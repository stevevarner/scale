"""Defines exceptions that can occur when conduction secrets transactions"""


class InvalidSecretsAuthorization(Exception):
    """Exception indicating that the provided credentials to a secrets request was invalid
    """
    pass


class InvalidSecretsConfiguration(Exception):
    """Exception indicating that the secrets backend is not properly configured
    """
    pass


class InvalidSecretsRequest(Exception):
    """Exception indicating that the secrets request was invalid
    """
    pass


class InvalidSecretsToken(Exception):
    """Exception indicating that the secrets token was invalid
    """
    pass


class InvalidSecretsValue(Exception):
    """Exception indicating that the secrets value was invalid
    """
    pass
