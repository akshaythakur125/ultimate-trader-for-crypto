class BingXError(Exception):
    pass


class BingXConnectionError(BingXError):
    pass


class BingXAuthError(BingXError):
    pass


class BingXRateLimitError(BingXError):
    pass


class BingXDataError(BingXError):
    pass


class BingXNotConfiguredError(BingXError):
    pass
