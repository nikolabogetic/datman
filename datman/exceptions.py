"""Defines the exceptions used by xnat sub-modules"""


class XnatException(Exception):
    """Default exception for xnat errors"""
    def __init__(self, msg, study=None, session=None):

        # Call the base class constructor with the parameters it needs
        super().__init__(msg)

        # Now for your custom args...
        self.study = study
        self.session = session


class DashboardException(Exception):
    """Default exception for dashboard errors"""
