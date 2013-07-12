#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

"""
plex-log-saver.py

Created by Jacob Smith on 2013-07-10.
Copyright (c) 2013 Jacob Smith. All rights reserved.

Mostly 'original' code by me, ported from memory of a perl script i wrote years ago.
Couldn't remember the O_EXCL part, found it on Evan Fosmark's excellent filelock code.
Not sure what copyright would apply here, so I am including evan's here.

######################################################################################

http://www.evanfosmark.com/2009/01/cross-platform-file-locking-support-in-python/

# Copyright (c) 2009, Evan Fosmark
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met: 
# 
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer. 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution. 
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies, 
# either expressed or implied, of the FreeBSD Project.

"""


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
            self.acquire()
            return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.file_handle is not None:
            self.release()

    def __del__(self):
        if self.file_handle is not None:
            self.release()


if __name__ == '__main__':
    with LockFile() as lf:
        print("Got lock, now sleeping...")
        time.sleep(3)
        print("Done!")
    time.sleep(0.1)

    for i in range(100):
        with LockFile() as lf:
            print("Trying again...", i)
            time.sleep(.5)
        time.sleep(0.1)
