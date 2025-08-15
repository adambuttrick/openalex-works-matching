import logging
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
from typing import List, Tuple, Dict, Optional
from functools import lru_cache


class AffiliationEmbeddingModel(torch.nn.Module):
    def __init__(self, model_path="cometadata/affiliation-clustering-0.3b"):
        super().__init__()
        try:
            logging.info(f"Loading affiliation embedding model from {model_path}")
            self.model = AutoModel.from_pretrained(model_path, trust_remote_code=True)
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            self.embedding_dim = 768
            self.model.eval()
            
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            logging.info(f"Model loaded successfully on {self.device}")
            
        except Exception as e:
            logging.error(f"Failed to load affiliation embedding model: {e}")
            raise
    
    def tokenize(self, input_texts: List[str]) -> dict:
        return self.tokenizer(
            input_texts,
            max_length=8192,
            padding=True,
            truncation=True,
            return_tensors='pt'
        )
    
    def forward(self, **inputs) -> torch.Tensor:
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        outputs = self.model(**inputs)
        embeddings = outputs.last_hidden_state[:, 0][:, :self.embedding_dim]
        embeddings = F.normalize(embeddings, p=2, dim=1)
        return embeddings
    
    @torch.no_grad()
    def get_embeddings(self, affiliations: List[str]) -> torch.Tensor:
        if not affiliations:
            return torch.tensor([])
        
        tokens = self.tokenize(affiliations)
        embeddings = self(**tokens)
        return embeddings
    
    @torch.no_grad()
    def compute_similarity(self, affiliation1: str, affiliation2: str) -> float:
        embeddings = self.get_embeddings([affiliation1, affiliation2])
        if len(embeddings) != 2:
            return 0.0
        
        similarity = (embeddings[0] @ embeddings[1]).item()
        return max(0.0, min(1.0, similarity))
    
    @torch.no_grad()
    def compute_batch_similarities(self, 
                                 query_affiliation: str, 
                                 candidate_affiliations: List[str]) -> List[float]:

        if not candidate_affiliations:
            return []
        
        all_affiliations = [query_affiliation] + candidate_affiliations
        embeddings = self.get_embeddings(all_affiliations)
        
        if len(embeddings) == 0:
            return [0.0] * len(candidate_affiliations)
        
        query_embedding = embeddings[0]
        candidate_embeddings = embeddings[1:]
        
        similarities = []
        for candidate_embedding in candidate_embeddings:
            similarity = (query_embedding @ candidate_embedding).item()
            similarities.append(max(0.0, min(1.0, similarity)))
        
        return similarities


class CachedAffiliationMatcher:
    def __init__(self, model_path="cometadata/affiliation-clustering-0.3b", cache_size=1024):
        self.model = AffiliationEmbeddingModel(model_path)
        self.cache_size = cache_size
        self._embedding_cache = {}
    
    @lru_cache(maxsize=10000)
    def _cached_similarity(self, aff1: str, aff2: str) -> float:
        return self.model.compute_similarity(aff1, aff2)
    
    def match_affiliation(self, 
                         input_affiliation: str, 
                         candidate_affiliation: str, 
                         threshold: float = 0.7) -> Tuple[bool, float]:
        
        if not input_affiliation or not candidate_affiliation:
            return False, 0.0
        
        input_norm = input_affiliation.strip().lower()
        candidate_norm = candidate_affiliation.strip().lower()
        
        if input_norm == candidate_norm:
            return True, 1.0
        
        similarity = self._cached_similarity(input_norm, candidate_norm)
        is_match = similarity >= threshold
        
        return is_match, similarity
    
    def find_best_match(self, 
                       query_affiliation: str, 
                       candidate_affiliations: List[str], 
                       threshold: float = 0.7) -> Optional[Tuple[str, float]]:

        if not query_affiliation or not candidate_affiliations:
            return None
        
        similarities = self.model.compute_batch_similarities(
            query_affiliation, 
            candidate_affiliations
        )
        
        best_score = 0.0
        best_match = None
        
        for candidate, score in zip(candidate_affiliations, similarities):
            if score >= threshold and score > best_score:
                best_score = score
                best_match = candidate
        
        if best_match:
            return best_match, best_score
        return None
    
    def clear_cache(self):
        self._cached_similarity.cache_clear()
        self._embedding_cache.clear()