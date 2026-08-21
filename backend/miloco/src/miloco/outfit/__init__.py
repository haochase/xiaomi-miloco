"""Outfit Agent domain package."""

from miloco.outfit.voice_contracts import (
    MAX_TRUSTED_SPEECH_AGE_MS,
    OutfitVoiceOutcome,
    SpeechTurnRejected,
    SpeechTurnRejectionReason,
    TrustedSpeechTurn,
    VoiceTurnStatus,
    validate_primary_person_id,
)

__all__ = [
    "MAX_TRUSTED_SPEECH_AGE_MS",
    "OutfitVoiceOutcome",
    "SpeechTurnRejected",
    "SpeechTurnRejectionReason",
    "TrustedSpeechTurn",
    "VoiceTurnStatus",
    "validate_primary_person_id",
]
