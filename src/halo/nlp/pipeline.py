"""
NLP Pipeline for Swedish text analysis.

Orchestrates all NLP components:
- Tokenization
- Named Entity Recognition
- Sentiment Analysis
- Threat Vocabulary Detection
- Text Summarization (GPT-SW3)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from halo.config import settings
from halo.nlp.ner import Entity, NamedEntityRecognizer
from halo.nlp.sentiment import SentimentAnalyzer, SentimentResult
from halo.nlp.threat_vocab import ThreatVocabularyDetector, VocabMatch
from halo.nlp.tokenizer import SwedishTokenizer

logger = logging.getLogger(__name__)


@dataclass
class NLPResult:
    """Complete result of NLP analysis."""

    # Input
    text: str
    language: str = "sv"

    # Entities
    entities: list[Entity] = field(default_factory=list)

    # Sentiment
    sentiment: Optional[SentimentResult] = None

    # Threat vocabulary
    vocab_matches: list[VocabMatch] = field(default_factory=list)

    # Summary (if generated)
    summary: Optional[str] = None

    # Metadata
    processed_at: datetime = field(default_factory=datetime.utcnow)
    processing_time_ms: float = 0.0
    model_versions: dict = field(default_factory=dict)

    @property
    def risk_score(self) -> float:
        """Calculate overall risk score from all components."""
        scores = []

        if self.sentiment:
            scores.append(self.sentiment.risk_score)

        if self.vocab_matches:
            # Weight by severity
            severity_weights = {"low": 0.2, "medium": 0.5, "high": 1.0}
            vocab_score = sum(
                severity_weights.get(m.severity, 0.5) for m in self.vocab_matches
            ) / max(1, len(self.vocab_matches))
            scores.append(vocab_score)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    @property
    def has_concerning_content(self) -> bool:
        """Check if any concerning content was detected."""
        if self.sentiment and self.sentiment.is_concerning:
            return True

        high_severity = [m for m in self.vocab_matches if m.severity == "high"]
        if high_severity:
            return True

        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/API response."""
        return {
            "text_length": len(self.text),
            "language": self.language,
            "entities": [
                {
                    "text": e.text,
                    "label": e.label,
                    "start": e.start,
                    "end": e.end,
                    "confidence": e.confidence,
                }
                for e in self.entities
            ],
            "sentiment": {
                "polarity": self.sentiment.polarity,
                "fear_score": self.sentiment.fear_score,
                "violence_score": self.sentiment.violence_score,
                "urgency_score": self.sentiment.urgency_score,
                "threat_score": self.sentiment.threat_score,
                "risk_score": self.sentiment.risk_score,
            }
            if self.sentiment
            else None,
            "vocab_matches": [
                {
                    "keyword": m.keyword,
                    "category": m.category,
                    "severity": m.severity,
                }
                for m in self.vocab_matches
            ],
            "summary": self.summary,
            "risk_score": self.risk_score,
            "has_concerning_content": self.has_concerning_content,
            "processed_at": self.processed_at.isoformat(),
            "processing_time_ms": self.processing_time_ms,
        }


class NLPPipeline:
    """
    Orchestrates NLP analysis for Swedish text.

    Usage:
        pipeline = NLPPipeline()
        result = pipeline.analyze("Din text här...")
    """

    def __init__(
        self,
        ner_model_path: Optional[Path] = None,
        summarizer_model_path: Optional[Path] = None,
        use_gpu: bool = False,
    ):
        """
        Initialize the NLP pipeline.

        Args:
            ner_model_path: Path to KB-BERT NER model
            summarizer_model_path: Path to GPT-SW3 model
            use_gpu: Whether to use GPU for inference
        """
        self.use_gpu = use_gpu

        # Initialize components
        self.tokenizer = SwedishTokenizer()
        self.ner = NamedEntityRecognizer(
            model_path=ner_model_path or settings.kb_bert_model_path,
            use_gpu=use_gpu,
        )
        self.sentiment = SentimentAnalyzer()
        self.threat_vocab = ThreatVocabularyDetector()

        # Summarizer is loaded lazily
        self._summarizer = None
        self._summarizer_path = summarizer_model_path or settings.gpt_sw3_model_path

        logger.info("NLP Pipeline initialized")

    def analyze(
        self,
        text: str,
        extract_entities: bool = True,
        analyze_sentiment: bool = True,
        detect_threats: bool = True,
        generate_summary: bool = False,
        max_summary_length: int = 150,
    ) -> NLPResult:
        """
        Run NLP analysis on text.

        Args:
            text: Input text
            extract_entities: Whether to run NER
            analyze_sentiment: Whether to run sentiment analysis
            detect_threats: Whether to run threat vocabulary detection
            generate_summary: Whether to generate a summary
            max_summary_length: Maximum summary length in words

        Returns:
            NLPResult with all analysis results
        """
        import time

        start_time = time.time()

        result = NLPResult(text=text)

        # Extract entities
        if extract_entities:
            try:
                result.entities = self.ner.extract_entities(text)
            except Exception as e:
                logger.error(f"Entity extraction failed: {e}")
                result.entities = []

        # Analyze sentiment
        if analyze_sentiment:
            try:
                result.sentiment = self.sentiment.analyze(text)
            except Exception as e:
                logger.error(f"Sentiment analysis failed: {e}")
                result.sentiment = None

        # Detect threat vocabulary
        if detect_threats:
            try:
                result.vocab_matches = self.threat_vocab.detect(text)
            except Exception as e:
                logger.error(f"Threat vocabulary detection failed: {e}")
                result.vocab_matches = []

        # Generate summary
        if generate_summary:
            try:
                result.summary = self._generate_summary(text, max_summary_length)
            except Exception as e:
                logger.error(f"Summary generation failed: {e}")
                result.summary = None

        result.processing_time_ms = (time.time() - start_time) * 1000
        result.model_versions = self._get_model_versions()

        return result

    def analyze_batch(
        self,
        texts: list[str],
        **kwargs,
    ) -> list[NLPResult]:
        """
        Analyze multiple texts.

        Args:
            texts: List of texts to analyze
            **kwargs: Arguments passed to analyze()

        Returns:
            List of NLPResult objects
        """
        return [self.analyze(text, **kwargs) for text in texts]

    def _generate_summary(self, text: str, max_length: int = 150) -> Optional[str]:
        """
        Generate a summary using GPT-SW3.

        Args:
            text: Input text
            max_length: Maximum summary length

        Returns:
            Summary text or None if unavailable
        """
        if self._summarizer is None:
            self._load_summarizer()

        if self._summarizer is None:
            # Fall back to extractive summary
            return self._extractive_summary(text, max_length)

        try:
            # Use GPT-SW3 for abstractive summary
            prompt = f"Sammanfatta följande text kort:\n\n{text[:2000]}\n\nSammanfattning:"

            inputs = self._summarizer["tokenizer"](
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )

            if self.use_gpu:
                import torch

                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}

            outputs = self._summarizer["model"].generate(
                **inputs,
                max_new_tokens=max_length,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
            )

            summary = self._summarizer["tokenizer"].decode(
                outputs[0], skip_special_tokens=True
            )

            # Extract just the summary part
            if "Sammanfattning:" in summary:
                summary = summary.split("Sammanfattning:")[-1].strip()

            return summary

        except Exception as e:
            logger.error(f"GPT-SW3 summary generation failed: {e}")
            return self._extractive_summary(text, max_length)

    def _extractive_summary(self, text: str, max_words: int = 50) -> str:
        """
        Generate extractive summary (first N sentences).

        Fallback when GPT-SW3 is not available.
        """
        sentences = self.tokenizer.sentence_tokenize(text)

        summary = []
        word_count = 0

        for sentence in sentences:
            words = sentence.split()
            if word_count + len(words) > max_words:
                break
            summary.append(sentence)
            word_count += len(words)

        return " ".join(summary)

    def _load_summarizer(self):
        """Load GPT-SW3 model for summarization."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            if self._summarizer_path.exists():
                logger.info(f"Loading GPT-SW3 from {self._summarizer_path}")
                tokenizer = AutoTokenizer.from_pretrained(str(self._summarizer_path))
                model = AutoModelForCausalLM.from_pretrained(str(self._summarizer_path))
            else:
                # Use smaller model from HuggingFace Hub
                model_name = "AI-Sweden-Models/gpt-sw3-126m"
                logger.info(f"Loading GPT-SW3 from {model_name}")
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModelForCausalLM.from_pretrained(model_name)

            if self.use_gpu:
                import torch

                if torch.cuda.is_available():
                    model = model.cuda()

            self._summarizer = {"model": model, "tokenizer": tokenizer}
            logger.info("GPT-SW3 loaded successfully")

        except Exception as e:
            logger.warning(f"Could not load GPT-SW3: {e}")
            self._summarizer = None

    def _get_model_versions(self) -> dict:
        """Get versions of loaded models."""
        versions = {
            "tokenizer": "swedish-1.0",
            "threat_vocab": "1.0",
        }

        if self.ner._model_loaded:
            versions["ner"] = "kb-bert-ner-1.0"

        if self._summarizer is not None:
            versions["summarizer"] = "gpt-sw3"

        return versions
