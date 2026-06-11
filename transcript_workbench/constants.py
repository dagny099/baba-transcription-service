"""Constants used across TranscriptWorkbench."""

# Streamlit-supported audio/video file extensions for the uploader.
SUPPORTED_AUDIO_EXTENSIONS: list[str] = [
    "mp3",
    "m4a",
    "mp4",
    "mpeg",
    "mpga",
    "wav",
    "webm",
    "ogg",
    "flac",
]

# Job status values.
JOB_STATUS_CREATED = "created"
JOB_STATUS_PREPROCESSING = "preprocessing"
JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

# Effective feature support statuses.
FEATURE_SUPPORTED = "supported"
FEATURE_PARTIAL = "partial"
FEATURE_PROXY = "proxy"
FEATURE_DIAGNOSTIC = "diagnostic"
FEATURE_UNSUPPORTED = "unsupported"
FEATURE_NOT_REQUESTED = "not_requested"

# Confidence types.
CONFIDENCE_WORD = "word_confidence"
CONFIDENCE_SEGMENT = "segment_confidence"
CONFIDENCE_TOKEN_LOGPROB = "token_logprob_proxy"
CONFIDENCE_SEGMENT_DIAGNOSTIC = "segment_diagnostic"
CONFIDENCE_NONE = "none"

# Artifact types tracked in the artifacts table.
ARTIFACT_TXT = "txt"
ARTIFACT_MD = "md"
ARTIFACT_JSON = "json"
ARTIFACT_RAW = "raw"
ARTIFACT_INPUT = "input"

# Per-provider hard file-size caps enforced at the provider API level.
# Used to decide whether to offer in-app compression before submission.
PROVIDER_MAX_UPLOAD_MB: dict[str, int] = {
    "openai": 25,
}
