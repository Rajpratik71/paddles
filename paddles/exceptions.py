
class PaddlesError(Exception):
    pass


class InvalidRequestError(PaddlesError, ValueError):
    url = '/errors/invalid/'


class ForbiddenRequestError(PaddlesError, RuntimeError):
    url = '/errors/forbidden/'


class ResourceNotFoundError(PaddlesError, ValueError):
    url = '/errors/not_found/'


class ResourceUnavailableError(PaddlesError, RuntimeError):
    url = '/errors/unavailable/'
