'''
Created on Feb 4, 2016

@author:  Allis Tauri <allista@gmail.com>
'''

import SubprocessBase
from BioUtils.SeqUtils import SeqView, pretty_rec_name

class SeqLoader(SubprocessBase.SubprocessBase):
    def __init__(self):
        super(SeqLoader, self).__init__()
        
    def _initialize(self): return True
    
    def _do_work(self, filenames):
        if not filenames: return 0
        db = SeqView()
        if db.load(unicode(f) for f in filenames):
            for sid in db.keys():
                self._con.send((sid, pretty_rec_name(db[sid])))
        return 0

if __name__ == '__main__':
    SeqLoader()