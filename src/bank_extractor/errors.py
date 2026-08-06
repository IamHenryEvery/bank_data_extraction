class ExtractionError(Exception):
    pass


class ConfigError(ExtractionError):
    pass


class ConsentError(ExtractionError):
    pass


class SessionError(ExtractionError):
    pass


class AdapterError(ExtractionError):
    pass


class ChannelUnavailable(AdapterError):
    pass


class ChannelFailed(AdapterError):
    pass


class ExportError(ExtractionError):
    pass
