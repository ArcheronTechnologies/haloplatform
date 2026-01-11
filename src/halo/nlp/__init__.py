"""
NLP module for Swedish text analysis.

Provides:
- Named Entity Recognition using KB-BERT
- Text summarization using GPT-SW3
- Swedish tokenization and decompounding
- Sentiment analysis (fear/violence detection)
- Criminal vocabulary detection
"""

from halo.nlp.pipeline import NLPPipeline, NLPResult
from halo.nlp.tokenizer import SwedishTokenizer
from halo.nlp.ner import NamedEntityRecognizer, Entity as NEREntity
from halo.nlp.sentiment import SentimentAnalyzer, SentimentResult
from halo.nlp.threat_vocab import ThreatVocabularyDetector

__all__ = [
    "NLPPipeline",
    "NLPResult",
    "SwedishTokenizer",
    "NamedEntityRecognizer",
    "NEREntity",
    "SentimentAnalyzer",
    "SentimentResult",
    "ThreatVocabularyDetector",
]
