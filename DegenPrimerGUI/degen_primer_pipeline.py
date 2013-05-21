# Copyright (C) 2012 Allis Tauri <allista@gmail.com>
# 
# degen_primer is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# degen_primer_gui is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
Created on Mar 4, 2013

@author: Allis Tauri <allista@gmail.com>
'''

import sys, os
import signal


#pipeline object
pipeline = None

_pid = -1
def sig_handler(signal, frame):
    if _pid != os.getpid(): return
    if pipeline is not None:
        pipeline.terminate()
        sleep(1)
    sys.exit(1)
#end def


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


if __name__ == '__main__':
    import multiprocessing.connection as mpc
    import argparse
    from time import sleep
    from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
    from DegenPrimer.Pipeline import Pipeline
    from DegenPrimer.AnalysisTask import AnalysisTask
    from DegenPrimer.DBManagementTask import DBManagmentTask
    from DegenPrimer.OptimizationTask import OptimizationTask
    
    sys.stderr = StreamEncoder(sys.stderr)
    sys.stdout = StreamEncoder(sys.stdout)
    
    _error_msg = 'This executable should only be called from ' \
                 'inside the DegenPrimerGUI.'
                 
    #check if it is run from a tty
    if sys.stdin.isatty():
        sys.stderr.write(_error_msg+'\n')
        sys.exit(1)
    
    #initialize pipeline
    pipeline = Pipeline()
    pipeline.register_task(DBManagmentTask())
    pipeline.register_task(OptimizationTask())
    pipeline.register_task(AnalysisTask())

    #set PID
    _pid = os.getpid()

    #setup signal handler
    signal.signal(signal.SIGINT,  sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)

    #command line arguments
    parser = argparse.ArgumentParser(_error_msg)
    conf_group = parser.add_argument_group('Preset configuration')
    conf_group.add_argument('port', metavar='number', 
                            type=int, nargs=1,
                            help='Port number to connect to.')
    args = parser.parse_args()
    port        = args.port[0]
    
    #try to connect to the given port
    connection = None
    try:
        connection = mpc.Client(('localhost', port), authkey="degen_primer_auth")
    except mpc.AuthenticationError, e:
        sys.stderr.write('Cannot connect to the port %d\n' % port)
        sys.stderr.write(e.message+'\n')
        sys.exit(2)
    
    #read in configuration
    options = connection.recv()
    config  = DegenPrimerConfig.from_options(options)
    
    #else, run the pipeline
    exit_code = pipeline.run(config) 
    if exit_code: #pass back collected reports
        connection.send(config.reports)
    else: connection.send(None)
    
    #close connection
    connection.close()
    
    #exit normally
    sys.exit(0 if exit_code >= 0 else 3)
#end