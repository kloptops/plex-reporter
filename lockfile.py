#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

import os
import sys
import time
import errno

class NotLockedException(Exception): pass
class TimeOut(Exception): pass

class LockFile(object):
    def __init__(self, file_name = '__lock__', time_out = 0):
        self.file_name = file_name
        self.file_handle = None
        self.time_out = time_out

    def acquire(self, time_out = None):
        if time_out is None:
            time_out = self.time_out

        if time_out == 0:
            while True:
                while os.path.isfile(self.file_name):
                    time.sleep(0.01)

                try:
                    self.file_handle = os.open(self.file_name, os.O_CREAT|os.O_RDWR|os.O_EXCL)
                except OSError as error:
                    self.file_handle = None
                    if error.errno == errno.EEXIST:
                        continue
                    raise
                return
        else:
            end_time = time.time() + time_out
            while True:
                while os.path.isfile(self.file_name):
                    if time.time() > end_time:
                        raise TimeOut()
                    time.sleep(0.001)

                try:
                    self.file_handle = os.open(self.file_name, os.O_CREAT|os.O_RDWR|os.O_EXCL)
                except OSError as error:
                    self.file_handle = None
                    if error.errno == errno.EEXIST:
                        continue
                    raise

                return

    def release(self):
        if self.file_handle is None:
            raise NotLockedException()
        os.close(self.file_handle)
        self.file_handle = None
        os.unlink(self.file_name)

    def __enter__(self):
        if self.file_handle is None:
            return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.file_handle is not None:
            return self.release()

    def __del__(self):
        if self.file_handle is not None:
            return self.release()


if __name__ == '__main__':
    with LockFile() as lf:
        print("Got lock, now sleeping...")
        time.sleep(10)
        print("Done!")
    time.sleep(0.1)

    for i in range(10):
        with LockFile() as lf:
            print("Trying again...", i)
            time.sleep(2)
        time.sleep(0.1)
