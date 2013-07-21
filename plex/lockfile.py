# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

__license__ = """

http://www.evanfosmark.com/2009/01/cross-platform-file-locking-support-in-python/

Copyright (c) 2009, Evan Fosmark
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are those
of the authors and should not be interpreted as representing official policies,
either expressed or implied, of the FreeBSD Project.

"""

"""
To test the code fairly well, do:

    for i in {1..5}; do python -m plex.lockfile & done

"""

import os
import time
import errno
from plex.util import PlexException


class TimeOutError(PlexException):
    pass


class LockFile(object):
    def __init__(self, file_name='__lock__', time_out=0):
        self.file_name = file_name
        self.file_handle = None
        self.time_out = time_out
        self.counter = 0

    def acquire(self, time_out=None):
        if self.file_handle is not None:
            self.counter += 1
            return

        if time_out is None:
            time_out = self.time_out

        if time_out == 0:
            while True:
                while os.path.isfile(self.file_name):
                    time.sleep(0.01)

                try:
                    self.file_handle = os.open(self.file_name, (
                        os.O_CREAT | os.O_RDWR | os.O_EXCL))
                    self.counter += 1
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
                        raise TimeOutError()
                    time.sleep(0.001)

                try:
                    self.file_handle = os.open(self.file_name, (
                        os.O_CREAT | os.O_RDWR | os.O_EXCL))
                    self.counter += 1
                except OSError as error:
                    self.file_handle = None
                    if error.errno == errno.EEXIST:
                        continue
                    raise

                return

    def release(self):
        self.counter -= 1
        if self.counter < 0:
            raise RuntimeError("Released LockFile too many times!")

        if self.counter == 0:
            os.close(self.file_handle)
            self.file_handle = None
            os.unlink(self.file_name)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def __del__(self):
        if self.file_handle is not None:
            # Hack! :D
            self.counter = 1
            self.release()


def main():
    if hasattr(os, 'getpid'):
        pid = os.getpid()
    else:
        import random
        pid = random.randint(1, 1000)

    lock_file = LockFile()
    print("{0}: Test 1".format(pid))
    with lock_file:
        print("{0}:     Got lock, now sleeping...".format(pid))
        time.sleep(3)
        print("{0}:     Done!".format(pid))
    time.sleep(0.1)

    print("{0}: Test 2".format(pid))
    for i in range(10):
        with lock_file:
            print("{0}:     Trying again... {1}".format(pid, i))
            time.sleep(.5)
        time.sleep(0.1)

    print("{0}: Test 3".format(pid))
    with lock_file:
        print("{0}:     Depth 1".format(pid))
        with lock_file:
            print("{0}:         Depth 2".format(pid))
            with lock_file:
                print("{0}:             Depth 3!".format(pid))
                time.sleep(0.5)


if __name__ == '__main__':
    main()
