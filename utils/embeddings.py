"""
Role detection using embeddings and keyword matching
"""
import os
import json
import logging
import re
import time
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import numpy as np
from openai import OpenAI
from sklearn.metrics.pairwise import cosine_similarity
from config import settings

logger = logging.getLogger(__name__)

# Simple persistent cache file for embeddings
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "embeddings_cache.json")
CACHE_LOCK_RETRY = 3

# Ensure OpenAI key is provided via env var OPENAI_API_KEY
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
_openai_client: Optional[OpenAI] = None
try:
    _openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else OpenAI()
except Exception:
    # fallback to default construction (will use env var if set)
    _openai_client = OpenAI()

def _ensure_cache_path():
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    if not os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)

def _load_cache() -> Dict[str, List[float]]:
    _ensure_cache_path()
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _save_cache(cache: Dict[str, List[float]]):
    # naive atomic write
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    os.replace(tmp, CACHE_PATH)

def _call_openai_batch(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    # Batch request: fewer API calls and lower latency per item
    if not texts:
        return []
    try:
        resp = _openai_client.embeddings.create(model=model, input=texts)
        embs = []
        for item in resp.data:
            # support both object.attr and dict-style access
            emb = getattr(item, "embedding", None)
            if emb is None:
                emb = item["embedding"]
            embs.append(emb)
        return embs
        
    except Exception as e:
        logger.error(f"OpenAI API call error: {e}")
        return []

def get_embedding(text: str, model: str = "text-embedding-3-small") -> np.ndarray:
    text_key = text.strip()
    cache = _load_cache()
    if text_key in cache:
        return np.array(cache[text_key], dtype=np.float32)
    # Request and store
    embedding = _call_openai_batch([text_key], model=model)[0]
    cache[text_key] = embedding
    _save_cache(cache)
    return np.array(embedding, dtype=np.float32)

def get_embeddings_batch(texts: List[str], model: str = "text-embedding-3-small") -> List[np.ndarray]:
    cache = _load_cache()
    results: List[np.ndarray] = []
    to_request: List[str] = []
    idx_map: Dict[int, int] = {}  # index in original -> index in to_request
    for i, t in enumerate(texts):
        key = t.strip()
        if key in cache:
            results.append(np.array(cache[key], dtype=np.float32))
        else:
            idx_map[i] = len(to_request)
            to_request.append(key)
            results.append(None)  # placeholder

    if to_request:
        embeddings = _call_openai_batch(to_request, model=model)
        # store to cache and fill results
        for orig_idx, req_idx in idx_map.items():
            emb = embeddings[req_idx]
            cache[to_request[req_idx]] = emb
            results[orig_idx] = np.array(emb, dtype=np.float32)
        _save_cache(cache)

    # results should be fully populated
    return results

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class RoleDetector:
    """
    Lightweight role detector using OpenAI embeddings + cosine similarity.
    Implements keyword-first matching to save API calls.
    """
    def __init__(self, roles_path: Optional[str] = None, similarity_threshold: float = 0.68):
        self.roles_path = roles_path or os.path.join(os.path.dirname(__file__), "..", "config", "roles.json")
        self.similarity_threshold = similarity_threshold
        self.roles: List[str] = []
        self.roles_data: Dict[str, List[str]] = {}  # category -> variations mapping
        self._role_embeddings: List[np.ndarray] = []
        self._load_roles_and_embeddings()

    def _load_roles_and_embeddings(self):
        """Load roles configuration and pre-compute embeddings"""
        if not os.path.exists(self.roles_path):
            logger.warning(f"Roles file not found: {self.roles_path}")
            self.roles = []
            self.roles_data = {}
            self._role_embeddings = []
            return
        
        try:
            with open(self.roles_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            canonical_roles: List[str] = []
            alias_groups: List[List[str]] = []

            if isinstance(data, dict):
                # mapping: canonical -> [aliases...]
                self.roles_data = data  # Store for keyword matching
                for canon, aliases in data.items():
                    canonical_roles.append(str(canon))
                    if isinstance(aliases, list):
                        alias_groups.append([str(canon)] + [str(a) for a in aliases])
                    else:
                        alias_groups.append([str(canon), str(aliases)])
            elif isinstance(data, list):
                # Convert list to dict format
                for item in data:
                    if isinstance(item, str):
                        canonical_roles.append(item)
                        alias_groups.append([item])
                        self.roles_data[item] = [item]
                    elif isinstance(item, dict) and "name" in item:
                        name = str(item["name"])
                        canonical_roles.append(name)
                        aliases = item.get("aliases") or item.get("variants") or []
                        if isinstance(aliases, list):
                            alias_groups.append([name] + [str(a) for a in aliases])
                            self.roles_data[name] = [name] + [str(a) for a in aliases]
                        else:
                            alias_groups.append([name, str(aliases)])
                            self.roles_data[name] = [name, str(aliases)]
            else:
                logger.error("Unexpected roles.json format; expected list or dict.")
                self.roles = []
                self.roles_data = {}
                self._role_embeddings = []
                return

            self.roles = canonical_roles
            if not self.roles:
                self._role_embeddings = []
                return

            # Flatten all unique texts to request embeddings in batches (cache-friendly)
            all_texts = []
            group_indices = []  # for each canonical, indices into all_texts
            for group in alias_groups:
                indices = []
                for t in group:
                    indices.append(len(all_texts))
                    all_texts.append(t)
                group_indices.append(indices)

            all_embs = get_embeddings_batch(all_texts) if all_texts else []
            
            # For each canonical role, average embeddings of its group
            role_embs = []
            for indices in group_indices:
                parts = [all_embs[i] for i in indices]
                if parts:
                    stacked = np.stack(parts, axis=0)
                    avg = np.mean(stacked, axis=0)
                    role_embs.append(avg)
                else:
                    role_embs.append(np.zeros((len(all_embs[0]) if all_embs else 1536,), dtype=np.float32))

            self._role_embeddings = role_embs

            logger.info(f"Loaded {len(self.roles)} role categories with keyword matching enabled")

        except Exception as e:
            logger.error(f"Failed to load roles or embeddings: {e}")
            self.roles = []
            self.roles_data = {}
            self._role_embeddings = []

    def _normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        # Convert to lowercase
        text = text.lower().strip()
        
        # Remove common prefixes/suffixes
        prefixes_to_remove = ['senior ', 'jr ', 'junior ', 'lead ', 'principal ', 'staff ']
        suffixes_to_remove = [' i', ' ii', ' iii', ' iv', ' v']
        
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):]
        
        for suffix in suffixes_to_remove:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
        
        # Clean up extra spaces and special characters
        text = re.sub(r'[^\w\s&+]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def _is_keyword_match(self, job_title: str, role_text: str) -> bool:
        """Check if there's a good keyword match between job title and role"""
        
        # Exact match
        if job_title == role_text:
            return True
        
        # Contains match (either direction)
        if role_text in job_title or job_title in role_text:
            return True
        
        # Word-by-word match for multi-word roles
        job_words = set(job_title.split())
        role_words = set(role_text.split())
        
        # High overlap threshold
        if len(role_words) > 1:
            overlap = len(job_words.intersection(role_words))
            overlap_ratio = overlap / len(role_words)
            if overlap_ratio >= 0.7:  # 70% of role words must match
                return True
        
        return False

    def _keyword_match(self, job_title: str) -> Optional[Tuple[str, str]]:
        """
        Try to match job title using keyword matching (NO API CALL)
        Returns (category, variation) if match found, None otherwise
        """
        normalized_title = self._normalize_text(job_title)
        
        # Direct category match
        for category in self.roles_data.keys():
            normalized_category = self._normalize_text(category)
            if normalized_category in normalized_title or normalized_title in normalized_category:
                logger.debug(f"Keyword match: '{job_title}' matched category '{category}'")
                return category, category
        
        # Variation match
        for category, variations in self.roles_data.items():
            # Check category name first
            normalized_category = self._normalize_text(category)
            if self._is_keyword_match(normalized_title, normalized_category):
                logger.debug(f"Keyword match: '{job_title}' matched category '{category}'")
                return category, category
            
            # Check variations
            for variation in variations:
                normalized_variation = self._normalize_text(variation)
                if self._is_keyword_match(normalized_title, normalized_variation):
                    logger.debug(f"Keyword match: '{job_title}' matched variation '{variation}' in category '{category}'")
                    return category, variation
        
        return None

    def _embedding_match(self, job_title: str, job_description: str = "") -> Optional[Tuple[str, str, float]]:
        """
        Try to match job title using embedding similarity (API CALL)
        Returns (category, variation, score) if match found, None otherwise
        """
        
        # Combine title and relevant parts of description for better context
        text_to_embed = job_title
        if job_description:
            # Extract first paragraph or first 200 chars of description for context
            desc_snippet = job_description.split('\n')[0][:200]
            text_to_embed = f"{job_title} {desc_snippet}"
        
        try:
            # Get embedding for job text (API CALL)
            logger.debug(f"Getting embedding for job title: '{job_title}' (keyword match failed)")
            job_emb = get_embedding(text_to_embed)
            
            best_idx = -1
            best_score = -1.0
            
            # Compare against all pre-computed role embeddings
            for i, role_emb in enumerate(self._role_embeddings):
                score = cosine_sim(job_emb, role_emb)
                if score > best_score:
                    best_score = score
                    best_idx = i
            
            # Check if similarity meets threshold
            if best_idx >= 0 and best_score >= self.similarity_threshold:
                category = self.roles[best_idx]
                logger.debug(f"Embedding match: '{job_title}' matched '{category}' with score {best_score:.3f}")
                return category, category, best_score
            else:
                logger.debug(f"No embedding match found for '{job_title}' (best score: {best_score:.3f}, threshold: {self.similarity_threshold})")
            
        except Exception as e:
            logger.error(f"Error in embedding matching: {e}")
        
        return None

    def detect_role(self, title: str, description: str = "") -> tuple:
        """
        Detect role category and variation for a job
        Returns: (category, variation, metadata)
        
        LOGIC:
        1. Try keyword matching first (NO API CALL)
        2. If keyword fails, try embedding matching (API CALL)
        3. If both fail, return "Unknown"
        """
        
        logger.debug(f"Detecting role for: {title}")
        
        detection_metadata = {
            'job_title': title,
            'method_used': None,
            'confidence_score': 0.0,
            'processing_steps': []
        }
        
        # Step 1: Try keyword matching first (FAST, NO API CALL)
        detection_metadata['processing_steps'].append('keyword_matching')
        keyword_result = self._keyword_match(title)
        
        if keyword_result:
            category, variation = keyword_result
            detection_metadata['method_used'] = 'keyword'
            detection_metadata['confidence_score'] = 1.0
            logger.info(f"Role detected via keyword matching: {category} -> {variation}")
            return category, variation, detection_metadata
        
        # Step 2: Try embedding matching (SLOWER, API CALL)
        detection_metadata['processing_steps'].append('embedding_matching')
        embedding_result = self._embedding_match(title, description)
        
        if embedding_result:
            category, variation, similarity_score = embedding_result
            detection_metadata['method_used'] = 'embedding'
            detection_metadata['confidence_score'] = similarity_score
            logger.info(f"Role detected via embedding matching: {category} -> {variation} (similarity: {similarity_score:.3f})")
            return category, variation, detection_metadata
        
        # Step 3: No match found
        logger.info(f"No role category found for: {title}")
        detection_metadata['method_used'] = 'none'
        return "Unknown", "Unknown", detection_metadata

    def get_role_categories(self) -> List[str]:
        """Get list of available role categories"""
        return self.roles.copy()

    def get_role_variations(self, category: str) -> List[str]:
        """Get variations for a specific role category"""
        return self.roles_data.get(category, [])

    # Expose embedding helpers for compatibility
    def embed_text(self, text: str) -> np.ndarray:
        return get_embedding(text)

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        return get_embeddings_batch(texts)

    def cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return cosine_sim(a, b)


# Global detector instance
_global_detector: Optional[RoleDetector] = None

def get_global_detector() -> RoleDetector:
    global _global_detector
    if _global_detector is None:
        _global_detector = RoleDetector()
    return _global_detector