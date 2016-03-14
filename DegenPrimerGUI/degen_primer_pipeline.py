#!/usr/bin/python
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

import SubprocessBase
from DegenPrimer.DegenPrimerConfig import DegenPrimerConfig
from DegenPrimer.Pipeline import Pipeline
from DegenPrimer.AnalysisTask import AnalysisTask
from DegenPrimer.OptimizationTask import OptimizationTask


class DegenPrimerSubprocess(SubprocessBase.SubprocessBase):
    '''Subprocess for DegenPrimer'''
    def __init__(self):
        super(DegenPrimerSubprocess, self).__init__()
        self._pipeline = None
    #end def
    
    def _initialize(self):
        self._pipeline = Pipeline(self._abort_event)
        self._pipeline.register_task(OptimizationTask(self._abort_event))
        self._pipeline.register_task(AnalysisTask(self._abort_event))
        return True
    #end def
    
    def _do_work(self, options):
        #read in configuration
        config = DegenPrimerConfig.from_options(options)
        #else, run the pipeline
        if self._pipeline.run(config) == 0: #pass back collected reports
            self._con.send(config.reports)
        return 0
    #end def
#end class


if __name__ == '__main__':
    DegenPrimerSubprocess()