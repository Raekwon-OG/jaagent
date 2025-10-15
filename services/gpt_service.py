"""
OpenAI GPT service with PII protection for job application processing
"""
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
import openai
from openai import OpenAI

from config import settings
from utils.pii_protection import pii_protector, secure_ai_processing

logger = logging.getLogger(__name__)

class GPTService:
    """OpenAI GPT service with PII protection and rate limiting"""
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")
        
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.chat_model = settings.CHAT_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Minimum seconds between requests
        
        logger.info(f"GPT Service initialized with model: {self.chat_model}")
    
    def _rate_limit(self):
        """Simple rate limiting to avoid hitting API limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    @secure_ai_processing
    def chat_completion(self, messages: List[Dict[str, str]], 
                       temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
        """
        Get chat completion from OpenAI with PII protection
        Messages should already be sanitized before calling this method
        """
        
        self._rate_limit()
        
        try:
            # Log the request for audit
            pii_protector.create_audit_log(
                operation="chat_completion",
                data_types=["resume", "job_description"],
                ai_service="openai"
            )
            
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            
            # Log token usage
            usage = response.usage
            logger.info(f"Chat completion - Input tokens: {usage.prompt_tokens}, "
                       f"Output tokens: {usage.completion_tokens}, "
                       f"Total: {usage.total_tokens}")
            
            return content
            
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            raise
    
    @secure_ai_processing
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text with PII protection"""
        
        self._rate_limit()
        
        try:
            # Log the request for audit
            pii_protector.create_audit_log(
                operation="get_embedding",
                data_types=["job_title", "text"],
                ai_service="openai"
            )
            
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            
            logger.debug(f"Generated embedding for text of length {len(text)}")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            raise
    
    def get_embeddings_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Get embeddings for multiple texts in batches"""
        
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                self._rate_limit()
                
                response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                
                batch_embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(batch_embeddings)
                
                logger.debug(f"Generated embeddings for batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
                
            except Exception as e:
                logger.error(f"Error in batch embedding {i//batch_size + 1}: {e}")
                # Continue with other batches
                all_embeddings.extend([[0.0] * 1536] * len(batch))  # Placeholder embeddings
        
        return all_embeddings
    
    def count_tokens(self, text: str) -> int:
        """Estimate token count for text (approximate)"""
        # Rough estimation: 1 token ≈ 4 characters for English text
        return len(text) // 4
    
    def truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately fit within token limit"""
        estimated_tokens = self.count_tokens(text)
        
        if estimated_tokens <= max_tokens:
            return text
        
        # Calculate approximate character limit
        char_limit = max_tokens * 4
        
        # Try to truncate at word boundary
        if len(text) > char_limit:
            truncated = text[:char_limit]
            last_space = truncated.rfind(' ')
            if last_space > char_limit * 0.8:  # If we can find a space near the end
                truncated = truncated[:last_space]
            
            logger.warning(f"Truncated text from {len(text)} to {len(truncated)} characters")
            return truncated + "..."
        
        return text
    
    def prepare_chat_messages(self, system_prompt: str, user_content: str, 
                            max_tokens: Optional[int] = None) -> List[Dict[str, str]]:
        """Prepare chat messages with token limit consideration"""
        
        if max_tokens:
            # Reserve tokens for system prompt and response
            system_tokens = self.count_tokens(system_prompt)
            response_tokens = 1000  # Reserve for response
            available_tokens = max_tokens - system_tokens - response_tokens
            
            if available_tokens > 0:
                user_content = self.truncate_text_to_tokens(user_content, available_tokens)
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    
    def validate_api_setup(self) -> List[str]:
        """Validate OpenAI API setup"""
        
        issues = []
        
        if not settings.OPENAI_API_KEY:
            issues.append("OpenAI API key not configured")
            return issues
        
        try:
            # Test chat completion
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'API test successful'"}
            ]
            
            response = self.chat_completion(test_messages, temperature=0)
            
            if "successful" not in response.lower():
                issues.append("Chat completion test failed - unexpected response")
            
        except Exception as e:
            issues.append(f"Chat completion test failed: {e}")
        
        try:
            # Test embedding
            embedding = self.get_embedding("test text")
            
            if not isinstance(embedding, list) or len(embedding) == 0:
                issues.append("Embedding test failed - invalid response format")
            
        except Exception as e:
            issues.append(f"Embedding test failed: {e}")
        
        return issues
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about current models"""
        
        return {
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "api_key_configured": bool(settings.OPENAI_API_KEY),
            "api_key_preview": settings.OPENAI_API_KEY[:10] + "..." if settings.OPENAI_API_KEY else None
        }


# Factory function for easy access
def create_gpt_service() -> GPTService:
    """Create a configured GPT service instance"""
    return GPTService()


# Global GPT service instance
_global_gpt_service: Optional[GPTService] = None

def get_global_gpt_service() -> GPTService:
    """Get or create the global GPT service instance"""
    global _global_gpt_service
    if _global_gpt_service is None:
        _global_gpt_service = create_gpt_service()
    return _global_gpt_service


# Convenience functions with automatic PII protection
def safe_chat_completion(system_prompt: str, user_content: str, 
                        candidate_info: Dict[str, str],
                        temperature: float = 0.7) -> Tuple[str, Dict[str, str]]:
    """
    Safe chat completion with automatic PII protection
    Returns: (response_with_pii_restored, replacement_mapping)
    """
    
    # Sanitize user content
    sanitized_content, replacement_mapping = pii_protector.sanitize_for_ai(user_content, candidate_info)
    
    # Prepare messages
    gpt_service = get_global_gpt_service()
    messages = gpt_service.prepare_chat_messages(system_prompt, sanitized_content)
    
    # Get response
    sanitized_response = gpt_service.chat_completion(messages, temperature=temperature)
    
    # Restore PII in response
    final_response = pii_protector.restore_pii(sanitized_response, replacement_mapping)
    
    return final_response, replacement_mapping

def safe_embedding(text: str, candidate_info: Optional[Dict[str, str]] = None) -> List[float]:
    """Safe embedding generation with PII protection"""
    
    if candidate_info:
        # Sanitize text
        sanitized_text, _ = pii_protector.sanitize_for_ai(text, candidate_info)
    else:
        sanitized_text = text
    
    gpt_service = get_global_gpt_service()
    return gpt_service.get_embedding(sanitized_text)


# Error handling and retry logic
class GPTServiceWithRetry:
    """GPT Service wrapper with retry logic for robustness"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.gpt_service = get_global_gpt_service()
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    def chat_completion_with_retry(self, messages: List[Dict[str, str]], 
                                  temperature: float = 0.7) -> str:
        """Chat completion with exponential backoff retry"""
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return self.gpt_service.chat_completion(messages, temperature)
                
            except openai.RateLimitError as e:
                last_exception = e
                delay = self.base_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)
                
            except openai.APIError as e:
                last_exception = e
                if "server" in str(e).lower():
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"Server error, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(delay)
                else:
                    # Non-retryable error
                    raise
                    
            except Exception as e:
                # Non-retryable error
                raise
        
        # All retries exhausted
        logger.error(f"All {self.max_retries} attempts failed")
        raise last_exception
    
    def embedding_with_retry(self, text: str) -> List[float]:
        """Embedding generation with retry logic"""
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return self.gpt_service.get_embedding(text)
                
            except openai.RateLimitError as e:
                last_exception = e
                delay = self.base_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                delay = self.base_delay * (2 ** attempt)
                logger.warning(f"Error in embedding, retrying in {delay}s: {e}")
                time.sleep(delay)
        
        raise last_exception


# Global retry service
def get_gpt_service_with_retry() -> GPTServiceWithRetry:
    """Get GPT service with retry logic"""
    return GPTServiceWithRetry()