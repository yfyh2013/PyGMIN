import numpy as np
from pygmin.storage import Database, Minimum, TransitionState
import argparse

def read_points_min_ts(fname, ndof=None, endianness="="):
    """
    read coords from a points.min or a points.ts file
    
    Notes
    -----
    the files were written with fortran code that looks something like this::
    
        NOPT = 3 * NATOMS
        INQUIRE(IOLENGTH=NDUMMY) COORDS(1:NOPT)
        OPEN(13,FILE='points.min,ACCESS='DIRECT',FORM='UNFORMATTED',STATUS='UNKNOWN',RECL=NDUMMY)
        DO J1=1,NMIN
            WRITE(13,REC=J1) COORDS(1:NOPT)
        ENDDO
        CLOSE(13) 
    
    This means the data is stored without any header information.  
    It is just a long list of double precision floating point numbers.
    
    Note that some fortran compilers use different endiness for the data.  If
    the coordinates comes out garbage this is probably the problem.  The solution
    is to pass a different data type
    
    dtype=np.dtype("<d")  # for little-endian double precision
    dtype=np.dtype(">d")  # for big-endian double precision
    
    Parameters
    ----------
    fname : str
        filenname to read from
    ndof : int, optional
        for testing to make sure the number of floats read is a multiple of ndof
    endianness : str
        define the endianness of the data. can be "=", "<", ">" 
     
    """
    with open(fname, "rb") as fin:
        coords = np.fromfile(fin, dtype=np.dtype(endianness+"d"))
    if ndof is not None:
        if len(coords) % ndof != 0:
                raise Exception("number of double precision variables read from %s is not divisible by ndof (%d)" % 
                                (fname, ndof) )
#    print coords
    return coords.flatten()

class Convert(object):
    '''
    Converts old OPTIM to pygmin database
    '''
    def __init__(self, ndof, db_name="Database.db", mindata="min.data", 
                  tsdata="ts.data", pointsmin="points.min", pointsts="points.ts",
                  endianness="="):
        self.ndof = ndof
        self.db_name = db_name
        self.mindata = mindata
        self.tsdata = tsdata
        self.pointsmin = pointsmin
        self.pointsts = pointsts
        self.endianness = endianness

        self.db = Database(self.db_name)
                
    def setAccuracy(self,accuracy = 0.000001):
        self.db.accuracy = accuracy
        
    def ReadMindata(self):
        print "reading from", self.mindata
        indx = 0
#        f_len = file_len(self.mindata)
        self.index2min = dict()
        for line in open(self.mindata,'r'):
            sline = line.split()
            
            # get the coordinates corresponding to this minimum
            coords = self.pointsmin_data[indx,:]
            
            # read data from the min.data line            
            e, fvib = map(float,sline[:2]) # energy and vibrational free energy
            pg = int(sline[2]) # point group order
            
            # create the minimum object and attach the data
            # must add minima like this.  If you use db.addMinimum()
            # some minima with similar energy might be assumed to be duplicates
            min1 = Minimum(e, coords)

            min1.fvib = fvib
            min1.pgorder = pg
            
            self.index2min[indx] = min1

            indx += 1
            self.db.session.add(min1)
            if indx % 500 == 0:
                self.db.session.commit()

    def ReadTSdata(self):
        print "reading from", self.tsdata

        indx = 0
        for line in open(self.tsdata,'r'):
            sline = line.split()

            # get the coordinates corresponding to this minimum
            coords = self.pointsts_data[indx,:]

            # read data from the min.ts line            
            e, fvib = map(float, sline[:2]) # get energy and fvib
            pg = int(sline[2]) # point group order
            m1indx, m2indx = map(int, sline[3:5]) 
            
            min1 = self.index2min[m1indx - 1] # minus 1 for fortran indexing
            min2 = self.index2min[m2indx - 1] # minus 1 for fortran indexing

            # must add transition states like this.  If you use db.addtransitionState()
            # some transition states might be assumed to be duplicates
            trans = TransitionState(e, coords, min1, min2)
            
            trans.fvib = fvib
            trans.pgorder = pg
            
            indx += 1
            self.db.session.add(trans)
            if indx % 500 == 0:
                self.db.session.commit()
        
    def read_points_min(self):
        print "reading from", self.pointsmin
        coords = read_points_min_ts(self.pointsmin, self.ndof, endianness=self.endianness)
        self.pointsmin_data = coords.reshape([-1, self.ndof])

    def read_points_ts(self):
        print "reading from", self.pointsts
        coords = read_points_min_ts(self.pointsts, self.ndof, endianness=self.endianness)
        self.pointsts_data = coords.reshape([-1, self.ndof])
                  
        
    def Convert(self):
        self.read_points_min()
        self.ReadMindata()
        self.db.session.commit()
        
        self.read_points_ts()
        self.ReadTSdata()
        self.db.session.commit()
    

    

def main():
    parser = argparse.ArgumentParser(description="""
convert an OPTIM database to a pygmin sqlite database.  Four files are needed.  Normally they are called:

    points.min : the coordinates of the minima in binary format
    min.data   : additional information about the minima (like the energy)
    points.ts  : the coordinates of the transition states
    min.ts     : additional information about transition states (like which minima they connect)

Other file names can optionally be passed.  Some fortran compilers use non-standard endianness to save the
binary data.  If your coordinates are garbage, try changing the endianness.
    """, formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument('ndof', help='Number of degrees of freedom (e.g. 3*number of atoms)', type = int)
    parser.add_argument('--Database','-d', help = 'Name of database to write into', type = str, default="optimdb.sqlite")
    parser.add_argument('--Mindata','-m', help = 'Name of min.data file', type = str, default="min.data")
    parser.add_argument('--Tsdata','-t', help = 'Name of ts.data file', type = str, default="ts.data")
    parser.add_argument('--Pointsmin','-p', help = 'Name of points.min file', type = str, default="points.min")
    parser.add_argument('--Pointsts','-q', help = 'Name of points.ts file', type = str, default="points.ts")
    parser.add_argument('--endianness', help = 'set the endianness of the binary data.  Can be "<" for little-endian or ">" for big-endian', type = str, default="=")
    args = parser.parse_args()
    
    cv = Convert(args.ndof, db_name=args.Database, mindata=args.Mindata, 
                 tsdata=args.Tsdata, pointsmin=args.Pointsmin, pointsts=args.Pointsts,
                 endianness=args.endianness)

    cv.setAccuracy()
     
    cv.Convert()
    cv.db.session.commit()


    
if __name__ == "__main__":
    main()

