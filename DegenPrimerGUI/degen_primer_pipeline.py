# Copyright (C) 2012 Allis Tauri <allista@gmail.com>
# 
# degen_primer is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# indicator_gddccontrol is distributed in the hope that it will be useful, but
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
degen_primer_pipeline = None

_pid = -1
def sig_handler(signal, frame):
    if _pid != os.getpid(): return
    degen_primer_pipeline.terminate()
    sleep(1)
    sys.exit(1)
#end def


if __name__ == '__main__':
    import multiprocessing.connection as mpc
    import argparse
    from time import sleep
    from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
    from DegenPrimer.DegenPrimerPipeline import DegenPrimerPipeline
    
    _error_msg = 'This executable should only be called from ' \
                 'inside the DegenPrimerGUI.'
                 
    #check if it is run from a tty
    if sys.stdin.isatty():
        sys.stderr.write(_error_msg+'\n')
        sys.exit(1)
    
    #initialize pipeline
    degen_primer_pipeline = DegenPrimerPipeline()
    
    #set PID
    _pid = os.getpid()

    #setup signal handler
    signal.signal(signal.SIGINT,  sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)

    #command line arguments
    parser = argparse.ArgumentParser(_error_msg)
    conf_group = parser.add_argument_group('Preset configuration')
    conf_group.add_argument('config_file', metavar='file.cfg', 
                            type=str, nargs=1,
                            help='Path to the analysis configuration file.')
    conf_group.add_argument('port', metavar='number', 
                            type=int, nargs=1,
                            help='Port number to connect to.')
    args = parser.parse_args()

    config_file = args.config_file[0]
    port        = args.port[0]
    
    #check configuragion file existance
    if not os.path.isfile(config_file):
        sys.stderr.write(('\nDegenPrimerPipeline subprocess: error, '
                          'configuration file "%s" does not exists.\n') % config_file)
        sys.exit(2)
               
    #try to connect to the given port
    connection = None
    try:
        connection = mpc.Client(('localhost', port), authkey="degen_primer_auth")
    except mpc.AuthenticationError, e:
        sys.stderr.write('Cannot connect to the port %d\n' % port)
        sys.stderr.write(e.message+'\n')
        sys.exit(3)
    
    #change working directory
    config_dir = os.path.dirname(config_file) or '.'
    os.chdir(config_dir)
    
    #read in configuration
    config = DegenPrimerConfig()
    try:
        config.parse_configuration(config_file)
    except ValueError, e:
        sys.stderr.write(e.message+'\n')
        sys.exit(4)
    
    #run the pipeline
    exit_code = degen_primer_pipeline.run(config)
    
    #pass back collected reports
    connection.send(config.reports)
    
    #close connection
    connection.close()
    
    #exit normally
    sys.exit(0)
#end