#!/usr/bin/env python


class FakeMontager(object):
    def __init__(self):
        pass

    def connect(self):
        pass

    def disconnect(self):
        pass

    def connected(self):
        return True

    def kill(self):
        pass
