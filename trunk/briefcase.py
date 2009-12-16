# -*- coding: latin-1 -*-

'''
    Briefcase Projekt v1.0 \n\
    Copyright � 2009-2010, Cristi Constantin. All rights reserved. \n\
    This module contains Briefcase class with all its functions. \n\
    Tested on Windows XP, with Python 2.6. \n\
    External dependencies : Python Crypto. \n\
'''

# Standard libraries.
import os, shutil
import glob
import sqlite3
import zlib
import cPickle
import tempfile
from time import clock

# External dependency.
from Crypto.Cipher import AES
from Crypto.Hash import MD4


class Briefcase:
    """ Main class """

    def __init__(self, database='Data.prv', password=''):
        '''
        Create new Database, or connect to an old Database. \n\
        If you don't know the correct password, you cannot acces the crypted data from tables,
        so don't delete the code that checks the password. Make sure you remember the password. \n\
        One SQLITE3 file for each Briefcase instance. \n\
        '''
        #
        self.database = database
        #
        if os.path.exists(database):
            exists_db = True
        else:
            exists_db = False

        self.conn = sqlite3.connect(self.database)
        self.c = self.conn.cursor()

        if exists_db:
            self.pwd = self.c.execute('select pwd from prv').fetchone()[0]
            if password != self.pwd:
                print('The password is INCORRECT! You will not be able to decrypt the data!')
                return -1
        else:
            md4 = MD4.new(password)
            self.pwd = password #md4.hexdigest()
            del md4
            self.c.execute('create table prv (pwd TEXT unique, file TEXT)')
            self.c.execute('insert into prv (pwd) values (?)', [self.pwd])
            self.conn.commit()
        #


    def _transformb(self, bdata):
        '''
        Transforms any binary data into ready-to-write SQL information.
        '''
        crypt = AES.new(self.pwd)
        vCompressed = zlib.compress(bdata,9)
        L = len(vCompressed)
        vCrypt = crypt.encrypt(vCompressed + 'X' * ((((L/16)+1)*16)-L))
        return buffer(vCrypt)


    def _restoreb(self, bdata):
        '''
        Restores binary data from SQL information.
        '''
        crypt = AES.new(self.pwd)
        vCompressed = crypt.decrypt(bdata)
        return zlib.decompress(vCompressed)


    def AddFile(self, filepath, versionable=True):
        '''
        If table doesn't exist, create the table. If table exists, add another row. \n\
        Table name is MD4 Hexdigest of the file name (lower case). \n\
        Each row contains : Version, Raw-data, Hash of original data. \n\
        Raw-data is : original binary data -> crypted -> compressed. \n\
        Versionable=False checks if the file is in the database. If it, an error is raised
        and the file is not added. \n\
        '''
        ti = clock()
        fpath = filepath.lower()
        md4 = MD4.new( os.path.split(fpath)[1] )
        filename = 't'+md4.hexdigest()
        del md4

        if not os.path.exists(filepath):
            print('File path "%s" doesn\'t exist! Cannot add file!' % filepath)
            return 1

        # Try to create the table.
        try:
            self.c.execute('create table %s (version integer primary key asc, raw blob, hash text)' %
                filename)
        # If the table is already created and versionable is false, raise error and exit. Else, pass.
        except:
            if not versionable:
                print('You selected versionable=False, so no new version will be added. '
                    'Will not add file!')
                return 1

        # Read and transform all binary data.
        f = open(filepath, 'rb').read()
        raw = self._transformb(f)
        md4 = MD4.new(f)
        hash = md4.hexdigest()
        del f, md4

        # Check if the new file is identical with the latest version.
        old_hash = self.c.execute('select hash from %s order by version desc' % filename).fetchone()
        if old_hash and hash == old_hash[0]:
            print('File "%s" is IDENTICAL with the version stored in the database. Will not add file!'
                % os.path.split(fpath)[1])
            return 1

        self.c.execute(('insert into %s (raw, hash) values (?,?)' % filename), [raw, hash])
        self.c.execute('insert or abort into prv (file) values (?)',
            [os.path.split(fpath.lower())[1]])
        self.conn.commit()

        ver_max = self.c.execute('select version from %s order by version desc' % filename).fetchone()
        print('Added file "%s" version "%i" in %.4f sec.' % (filepath, ver_max[0], clock()-ti))
        return 0


    def AddManyFiles(self, path, extensions, recursive, versionable=True):
        '''
        TODO
        Add more files, using patterns.
        '''
        pass


    def CopyIntoNew(self, fname, version, new_fname):
        '''
        TODO
        Copy one version of one file, into a new file, that will have version 1.
        '''
        pass


    def GetVersion(self, fname):
        '''
        Return an integer, representing the most recent version of the file. \n\
        All versions, from 1, to this number must be valid. \n\
        When a version is deleted, the file table is re-indexed. \n\
        '''
        md4 = MD4.new( fname.lower() )
        filename = 't'+md4.hexdigest()
        del md4

        try:
            highest_version = self.c.execute('select version from %s order by version desc' %
                filename).fetchone()
            return highest_version[0]
        except:
            highest_version = False
            print('Cannot find the file called "%s"!' % fname)
            return -1


    def ExportFile(self, fname, path='', version=0, execute=True):
        '''
        Call one file from the briefcase. \n\
        If version is not null, that specific version is used. Else, it's the most recent version. \n\
        If execute is false, the file is simply exported into the specified path.
        Else, the file is executed from a temporary folder, then the folder is deleted. \n\
        '''
        ti = clock()
        md4 = MD4.new( fname.lower() )
        filename = 't'+md4.hexdigest()
        del md4

        # If version is a positive number, get that version.
        if version and version > 0:
            try:
                selected_version = self.c.execute('select raw from %s order by version desc where '
                    ' version=%s' % (filename, version)).fetchone()
            except:
                selected_version = False
            # If the version doesn't exist, exit.
            if not selected_version:
                print('Cannot find version "%i" for file "%s"! Cannot execute.' % (version, fname))
                return 1
        # Else, get the latest version.
        else:
            try:
                selected_version = self.c.execute('select raw from %s order by version desc' %
                    filename).fetchone()
            except:
                selected_version = False
            # If the file doesn't exist, exit.
            if not selected_version:
                print('Cannot find the file called "%s"! Cannot execute.' % fname)
                return 1

        # If the path is specified, use it. Else, use a temp dir.
        if path:
            filename = path + '\\' + fname
        else:
            f = tempfile.mkdtemp('__', '__py')
            filename = f + '\\' + filename + os.path.splitext(fname)[1]
            del f

        w = open(filename, 'wb')
        w.write(self._restoreb(selected_version[0]))
        w.close() ; del w
        print( 'Exporting file "%s" took %.4f sec.' % (fname, clock()-ti) )

        # If execute, call the file, then delete it.
        if execute:
            os.system('"%s"&exit' % filename)
            os.remove(filename)
        # If not path, delete the temp folders.
        if not path:
            dirs = glob.glob(tempfile.gettempdir() + '\\' + '__py*__')
            for dir in dirs: shutil.rmtree(dir)
        return 0


    def ExportAll(self, path):
        '''
        Export all files into one folder. \n\
        Only the most recent version of each file is exported. \n\
        '''
        #
        ti = clock()
        #
        if not os.path.exists(path):
            print('Path "%s" doesn\'t exist! Cannot export folder!' % path)
            return 1

        all_files = self.c.execute('select file from prv order by file').fetchall()[1:]
        for temp_file in all_files:
            md4 = MD4.new(temp_file[0])
            filename = 't'+md4.hexdigest()
            latest_version = self.c.execute('select raw from %s order by version desc' %
                filename).fetchone()
            filename = path + '\\' + temp_file[0]
            w = open(filename, 'wb')
            w.write(self._restoreb(latest_version[0]))
            w.close()

        print( 'Exporting all files took %.4f sec.' % (clock()-ti) )
        return 0


    def RenFile(self, fname, new_fname):
        '''
        Rename one file. This cannot be undone.
        '''
        ti = clock()
        if ('\\' in new_fname) or ('/' in new_fname) or (':' in new_fname) or ('*' in new_fname) \
            or ('?' in new_fname) or ('"' in new_fname) or ('<' in new_fname) or ('>' in new_fname) \
            or ('|' in new_fname):
            print('A filename cannot contain any of the following characters  \\ / : * ? " < > | .'
                'Cannot rename file.')
            return 1

        md4 = MD4.new( fname.lower() )
        filename = 't'+md4.hexdigest()
        del md4
        md4 = MD4.new( new_fname.lower() )
        new_filename = 't'+md4.hexdigest()
        del md4

        try:
            self.c.execute('alter table %s rename to %s' % (filename, new_filename))
            self.c.execute('update prv set file="%s" where file="%s"' % (new_filename, filename))
            print( 'Renaming from "%s" into "%s" took %.4f sec.' % (fname, new_fname, clock()-ti) )
            return 0
        except:
            print('Cannot find the file called "%s"!' % fname)
            return 1


    def DelFile(self, fname, version=0):
        '''
        If version is a positive number, only that version of the file is deleted. \n\
        Else, the entire table is dropped. \n\
        '''
        ti = clock()
        md4 = MD4.new( fname.lower() )
        filename = 't'+md4.hexdigest()
        del md4

        if version and version > 0:
            self.c.execute('delete from %s where version=%s' % (filename, version))
            self.c.execute('reindex %s' % filename)
            print( 'Deleted file "%s" version "%i" in %.4f sec.' % (fname, version, clock()-ti) )
        else:
            self.c.execute('drop table if exists %s' % filename)
            self.c.execute('delete from prv where file="%s"' % fname.lower())
            print( 'Deleted file "%s" in %.4f sec.' % (fname, clock()-ti) )

        self.conn.commit()
        return 0


#


# Eof()