# coding=utf-8
#
# Copyright (C) 2013 Allis Tauri <allista@gmail.com>
# 
# DegenPrimerGUI is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# DegenPrimerGUI is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

'''
Created on Nov 10, 2013

@author: Allis Tauri <allista@gmail.com>
'''

import os
import sys
import abc
import signal
import argparse
import traceback
import multiprocessing.connection as mpc
import BioUtils.Tools.tmpStorage as tmpStorage
from BioUtils.Tools.UMP import ignore_interrupt
from multiprocessing.managers import SyncManager
from threading import Thread
from time import sleep


class SignalListener(Thread):
    def __init__(self, connection, event, sig='ABORT'):
        Thread.__init__(self)
        self.daemon  = 1
        self._con    = connection
        self._event  = event
        self._signal = sig
    #end def
    
    def _handle_signal(self):
        sig = self._con.recv()
        if sig == self._signal:
            self._event.set()
    #end def
    
    def run(self):
        try: self._handle_signal() 
        except (KeyboardInterrupt, EOFError, IOError): pass
        except Exception: traceback.print_exc()
    #end def
#end class

class StreamEncoder(object):
    encoding = 'UTF-8'
    
    def __init__(self, stream):
        self._stream = stream
        
    def write(self, text):
        encoded = unicode(text).encode(self.encoding)
        self._stream.write(encoded)
    
    def flush(self):
        self._stream.flush()
        
    def isatty(self):
        return self._stream.isatty()
#end class


class SubprocessBase(object):
    '''Base class for subprocess routines that use socket connection'''
    __metaclass__ = abc.ABCMeta
    
    _error_msg = ('This executable should only be called from '
                  'inside the main program.')
                 
    def __init__(self):
        self._pid  = os.getpid()
        #abort event
        self._mgr  = SyncManager()
        self._mgr.start(ignore_interrupt)
        self._abort_event = self._mgr.Event()
        #stdout/err
        self._err  = StreamEncoder(sys.stderr)
        self._out  = StreamEncoder(sys.stdout)
        #connection information
        self._port = None
        self._con  = None
        self()
    #end def
    
    def __del__(self):
        if self._con is not None:
            self.terminate()
            self._con.close()
        self._mgr.shutdown()
    #end def
    

    def _check_tty(self):
        if sys.stdin.isatty():
            self._err.write(self._error_msg+'\n')
            return True
        return False
    #end def
    
    def _sig_handler(self, signal, frame):
        if self._pid != os.getpid(): return
        self._out.write('%d aborting...\n'%os.getpid())
        self._abort_event.set(); sleep(0.1)
        tmpStorage.clean_tmp_files()
    #end def
        
    def _set_sig_handlers(self):
        signal.signal(signal.SIGINT,  self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)
        signal.signal(signal.SIGQUIT, self._sig_handler)
    #end def
    
    
    def _parse_args(self):
        parser = argparse.ArgumentParser(self._error_msg)
        conf_group = parser.add_argument_group('Preset configuration')
        conf_group.add_argument('port', metavar='number', 
                                type=int, nargs=1,
                                help='Port number to connect to.')
        args = parser.parse_args()
        self._port = args.port[0]
    #end def
    
    def _get_auth_key(self):
        try: self._auth = sys.stdin.readline().strip('\n')
        except: self._auth = None
    #end def
    
    def _connect(self):
        if self._port is None: return False
        try: self._con = mpc.Client(('localhost', self._port), 
                                    authkey=self._auth)
        except mpc.AuthenticationError, e:
            self._err.write('Cannot connect to the port %d\n%s\n' % (self._port,str(e)))
            return False
        except: 
            traceback.print_exc()
            return False
        return True
    #end def
    
    def _report_to_server(self):
        if self._con is None: return
        self._con.send(None)
    #end def
    
    def _disconnect(self):
        if self._con is None: return
        self._con.close()
        self._con = None
    #end def
    
    
    @abc.abstractmethod
    def _initialize(self): pass
    
    @abc.abstractmethod
    def _do_work(self, data): pass

    
    def _main(self):
        #check if run from a tty
        if self._check_tty(): return 1 
        #set std streams
        sys.stderr = self._err
        sys.stdout = self._out
        #set signal handlers
        self._set_sig_handlers()
        #initialize
        if not self._initialize():
            print 'Unable to initialize.\n'
            return 2
        #parse commandline arguments
        self._parse_args()
        #get auth key
        self._get_auth_key()
        #try to connect and get data
        if not self._connect(): return 3
        data = self._con.recv()
        #start abort signal listener
        abort_listner = SignalListener(self._con, self._abort_event)
        abort_listner.start()
        #do the work, report back
        result = self._do_work(data)
        self._report_to_server()
        #join abort listener
        abort_listner.join()
        #close connection
        self._disconnect()
        return 0 if result == 0 else 3+result
    #end def
    
    def __call__(self, sys_exit=True, *args, **kwargs):
        try: ret = self._main()
        except SystemExit, e:
            if sys_exit: sys.exit(e.code)
            else: return e.code
        except:
            traceback.print_exc()
            if sys_exit: sys.exit(1)
            else: return 1
        if sys_exit: sys.exit(ret or 0)
        else: return 0
#end class