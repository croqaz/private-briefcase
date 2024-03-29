# -*- coding: latin-1 -*-

'''
    Briefcase-Project v1.0 \n\
    Copyright (C) 2009-2012, Cristi Constantin. All rights reserved. \n\
    This module contains Briefcase class with all its functions. \n\
    Tested on Windows XP, Windows 7 and Ubuntu, with Python 2. \n\
    External dependencies : Python Crypto. \n\
'''

'''
    Every briefcase file is an SQLITE3 database containing tables : \n\
    - _info_ table : pwd BLOB, date TEXT, user TEXT, version TEXT; \n\
        it stores global password for database (hashed), date created, version of briefcase software. \n\
    - _files_ table : file TEXT unique, pwd BLOB, labels TEXT; \n\
        it stores the original name of files, hashed password and the labels. \n\
    - _statistics_ table : \n\
        file TEXT unique, size0 INTEGER, size INTEGER, sizeB INTEGER, date0 TEXT, date TEXT,
        user0 TEXT, user TEXT, labels TEXT; \n\
        it stores information about every file, everytime a file is added or removed. \n\
    - _logs_ table : \n\
        _logs_ (date TEXT, msg TEXT); \n\
        all actions can be stored in here. \n\
    - other tables, one table for each new file : \n\
        version integer primary key asc, raw BLOB, hash TEXT, size INTEGER, date TEXT, user TEXT. \n\
'''

'''
    In the database, is stored PBKDF2(password=user_password, salt='briefcase', dkLen=16, count=5000). \n\
    This value is compared with the password typed by the user. \n\
    For encrypting files, another PBKDF2 is used, with a random salt. The salt will be stored in DB. \n\
    So, only the password check and the salt are stored. \n\
'''

# Standard libraries.
import os, sys
import re
import glob
import shutil
import sqlite3
import zlib, bz2
import tempfile
import thread
import subprocess
from time import clock
from time import strftime

# External dependency.
from Crypto.Cipher import AES
from Crypto.Hash import MD4
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes

__version__ = 'r77'
__all__ = ['Briefcase', 'destroy_file', '__version__']

#

EXEC_info_ = 'create table if not exists _info_ (pwd BLOB, salt BLOB, date TEXT, user TEXT, version TEXT)'
EXEC_files_ = 'create table if not exists _files_ (file TEXT unique, pwd BLOB, labels TEXT)'
EXEC_statistics_ = 'create table if not exists _statistics_ (file TEXT unique, size0 INTEGER, size INTEGER, sizeB INTEGER, date0 TEXT, date TEXT, user0 TEXT, user TEXT, labels TEXT)'
EXEC_logs_ = 'create table if not exists _logs_ (date TEXT, msg TEXT)'

#

def validFileName(fname):
    if ('\\' in fname) or ('/' in fname) or (':' in fname) or ('*' in fname) \
        or ('?' in fname) or ('"' in fname) or ('<' in fname) or ('>' in fname) \
        or ('|' in fname):
        return False
    else:
        return True


def validPassword(user_pwd, old_check):
    # If both are false, the check is OK
    if not user_pwd and not old_check:
        return True
    new_check = PBKDF2(password=user_pwd, salt='briefcase', dkLen=16, count=5000).decode('latin-1')
    if new_check == old_check:
        return True
    else:
        return False


def threaded_execute(filename):
    '''
    Executes filename,
    '''
    if os.name=='posix':
        # On Unix systems, the execution is not blocking and will return immediately
        # So the cleanup must be done manually, by calling "destroy_file".
        subprocess.call(['xdg-open', filename])

    elif os.name=='nt':
        # On Windows, the execution is blocking
        os.system('"%s"&exit' % filename)
        # After the user closes the file, the file is destroyed
        destroy_file(filename)
        # Delete temp file
        try:
            shutil.rmtree(os.path.split(filename)[0])
        except:
            pass

    else:
        print('System not supported : `%s` !' % os.name)
        return -1

    return 0


def destroy_file(filename):
    # Open file in Append mode
    w = open(filename, 'a+', 0)
    w.seek(-1, 2)      # Go at the end in the file
    ovr_len = w.tell() # How many bytes to overwrite
    w.truncate(0)      # Truncate the file to zero
    w.write(get_random_bytes(ovr_len))
    print('Overwritten file `%s`, %i bytes.' % (filename, ovr_len))
    w.close() ; del w
    os.remove(filename) # Del file

#

class Briefcase:
    """ Main class """

    def __init__(self, database='Data.prv', password=''):
        '''
        Create new Database, or connect to an old Database. \n\
        If you don't know the correct password, you cannot acces the crypted data from tables. \n\
        Just make sure you remember the password. \n\
        Valid passwords : a string, a null value, or False. \n\
        One SQLITE3 file is used for each Briefcase instance. \n\
        '''
        #
        if password and not type(password) == type('') or type(password) == type(u''):
            raise Exception('The password must be a string! You provided type `%s`! Exiting!' % \
                str(type(password)))
            return
        # If password is null, the key and the salt must be null.
        elif not password:
            password = u''
            new_check = u''
            self.glob_key = u''
            self.glob_salt = u''
        #
        global __version__
        self.database = str(database)
        self.verbose = 2
        #
        if os.path.exists(self.database):
            exists_db = True
        else:
            exists_db = False
        #
        self.conn = sqlite3.connect(self.database)
        self.c = self.conn.cursor()
        #

        # If existing DB, must check the password. The password can be null.
        if exists_db:
            # Both the hash and the salt can be null.
            old_check = self.c.execute('select pwd from _info_').fetchone()[0]
            self.glob_salt = self.c.execute('select salt from _info_').fetchone()[0]

            # Validate user password.
            if not validPassword(password, old_check):
                raise Exception('The password is INCORRECT! Exiting!')
                return

        # If user provided a password and new DB, generate salt.
        elif password and not exists_db:
            new_check = PBKDF2(password=password, salt='briefcase', dkLen=16, count=5000).decode('latin-1')
            self.glob_salt = buffer(get_random_bytes(32))

        # If password was provided, calculate key derivation used for encryption.
        if password:
            self.glob_key = PBKDF2(password=password, salt=self.glob_salt, dkLen=32, count=1000)

        global EXEC_info_, EXEC_files_, EXEC_statistics_, EXEC_logs_
        # Create _info_ table with database password, date created and user.
        self.c.execute(EXEC_info_)
        # Create _files_ table with original names of the files and hashed passwords.
        self.c.execute(EXEC_files_)
        # Create _statistics_ table.
        self.c.execute(EXEC_statistics_)
        # Create _logs_ table.
        self.c.execute(EXEC_logs_)

        # If new DB, add password hash and salt in INFO table. Both the hash and the salt can be null.
        if not exists_db:
            self.c.execute('insert into _info_ (pwd, salt, date, user, version) values (?,?,?,?,?)',
                [new_check, self.glob_salt, strftime("%Y-%b-%d %H:%M:%S"), os.getenv('USERNAME'), __version__])
            self.c.execute('insert into _logs_ (date, msg) values (?,?)',
            [strftime("%Y-%m-%d %H:%M:%S"), ('Username "%s" creates database.' % os.getenv('USERNAME'))])
        # If existing DB, write some logs.
        else:
            self.c.execute('insert into _logs_ (date, msg) values (?,?)',
            [strftime("%Y-%m-%d %H:%M:%S"), ('Username "%s" opens database.' % os.getenv('USERNAME'))])

        #
        self.conn.commit()
        #


    def _transformb(self, bdata, pwd='', arch='zlib'):
        '''
        Transforms any binary data into ready-to-write SQL information. \n\
        zlib is faster, bz2 is stronger. \n\
        '''
        if arch=='bz2':
            vCompressed = bz2.compress(bdata,6)
        else:
            vCompressed = zlib.compress(bdata,9)
        # If password is null in some way, do not encrypt.
        if not pwd:
            return buffer(vCompressed)
        # If using global password.
        elif pwd == 1:
            # If global password is null, do not encrypt.
            if not self.glob_key:
                return buffer(vCompressed)
            # If global password exists, use it.
            else:
                pwd = self.glob_key
        # If password is provided, generate key derivation.
        else:
            pwd = PBKDF2(password=pwd, salt=self.glob_salt, dkLen=32, count=1000)
        # Encrypt and return.
        crypt = AES.new(pwd)
        padding = 'X' * ( (((len(vCompressed)/16)+1)*16) - len(vCompressed) )
        vCrypt = crypt.encrypt(vCompressed + padding)
        return buffer(vCrypt)


    def _restoreb(self, bdata, pwd=''):
        '''
        Restores binary data from SQL information. \n\
        '''
        # If password is null in some way, do not encrypt.
        if not pwd:
            try: return zlib.decompress(bdata)
            except: return bz2.decompress(bdata)
        # If using global password.
        elif pwd == 1:
            # If global password is null, do not decrypt.
            if not self.glob_key:
                try: return zlib.decompress(bdata)
                except: return bz2.decompress(bdata)
            # If global password exists, use it.
            else:
                pwd = self.glob_key
        # If password is provided, generate key derivation.
        else:
            pwd = PBKDF2(password=pwd, salt=self.glob_salt, dkLen=32, count=1000)
        # Decrypt and return.
        crypt = AES.new(pwd)
        vCompressed = crypt.decrypt(bdata)
        try: return zlib.decompress(vCompressed)
        except: return bz2.decompress(vCompressed)


    def _log(self, level, msg, log=True):
        '''
        Prints debug and error messages. \n\
        level 1 = info message, level 2 = fatal error. \n\
        verbose 0 = silence, verbose 1 = print errors, verbose 2+ = print all. \n\
        '''

        if log:
            self.c.execute('insert into _logs_ (date, msg) values (?,?)',
                [strftime("%Y-%m-%d %H:%M:%S"), msg])

        if self.verbose <= 0:
            # Don't print anything.
            return 0
        elif self.verbose == 1:
            # Only errors are printed.
            if level == 2:
                print( msg )
                return 1
        elif self.verbose >= 2:
            # All messages are logged.
            print( msg )
            return 2


    def SetLabels(self, fname, labels):
        '''
        Set labels/ tags/ keywords for one file. Labels can be used to sort and filter files. \n\
        Labels must be : ";" separated string, a list, or a tuple. \n\
        Any character excepting ";" can be used as label. \n\
        '''
        ti = clock()

        if not labels:
            self.c.execute('update _files_ set labels=? where file=?', ['', fname])
            return 0

        if type(labels) == type('') or type(labels) == type(u''):
            lLabels = sorted([s.strip() for s in labels.split(';')])
            sLabels = ';'.join(lLabels)
        elif type(labels) == type([0,0]) or type(labels) == type((0,0)):
            lLabels = sorted([s.strip() for s in labels])
            sLabels = ';'.join(lLabels)
        else:
            self._log(2, 'Func SetLabels: invalid type for the label! It must be : string, unicode, '
                'list, or tuple. You provided type "%s".' % type(labels))
            return -1

        # If file doesn't exist in database, exit.
        if not self.c.execute('select file from _files_ where file=?', [fname]).fetchone():
            self._log(2, 'Func SetLabels: file "%s" doesn\'t exist!' % fname)
            return -1

        # Update labels in _tables_.
        self.c.execute('update _files_ set labels=? where file=?', [sLabels, fname])
        self.conn.commit()
        self._log(1, 'Setting labels for file "%s" took %.4f sec.' % (fname, clock()-ti))
        return 0


    def AddFile(self, filepath, password=1, labels='', arch='zlib', versionable=True):
        '''
        If file doesn't exist in database, create the file. If file exists, add another row. \n\
        Table name is "t" + MD4 Hexdigest of the file name. \n\
        Each row contains : Version, Raw-data, Hash of original data, Size, Date Time, User Name. \n\
        Raw-data is : original binary data -> compressed -> crypted. \n\
        Versionable=False checks if the file is in the database. If it is, an error is raised
        and the file is not added. \n\
        '''
        ti = clock()
        fname = os.path.split(filepath)[1]
        arch = arch.lower()

        if not os.path.exists(filepath):
            self._log(2, 'Func AddFile: file path "%s" doesn\'t exist!' % filepath)
            return -1
        if arch != 'zlib':
            arch = 'bz2'

        # If password is a string or unicode, calculate the hash.
        if type(password) == type('') or type(password) == type(u''):
            pwd_hash = buffer(PBKDF2(password=password, salt='briefcase', dkLen=16, count=5000))
        # If password is database default, do nothing.
        elif password == 1:
            pwd_hash = 1
        # If password is null in some way, hash must be also null.
        else:
            password = None
            pwd_hash = None

        filename = 't'+MD4.new(fname).hexdigest()

        old_pwd_hash = self.c.execute('select pwd from _files_ where file="%s"' % fname).fetchone()

        # If the file exists and used doesn't want new versions, exit.
        if old_pwd_hash and not versionable:
            self._log(2, 'Func AddFile: you selected versionable=False, so new version will NOT be added!')
            return -1
        # If file exists in DB and user provided a password.
        elif old_pwd_hash and password:
            old_pwd_hash = old_pwd_hash[0]
            # If password from user is differend from password in DB, exit.
            if old_pwd_hash != pwd_hash:
                self._log(2, 'Func AddFile: The password is INCORRECT! You will not be able to '\
                    'decrypt/ encrypt any data!')
                return -1

        self.c.execute('create table if not exists %s (version integer primary key asc, raw BLOB,'\
            'hash TEXT, size INTEGER, date TEXT, user TEXT)' % filename)

        # File size.
        size = os.path.getsize(filepath)
        # Read and transform all binary data.
        f = open(filepath, 'rb').read()
        # This is the raw data.
        raw = self._transformb(f, password, arch)
        md4 = MD4.new(f)
        # This is the hash of the original file.
        new_hash = md4.hexdigest()
        del f, md4

        # Check if the new file is identical with the latest version.
        old_hash = self.c.execute('select hash from %s order by version desc' % filename).fetchone()
        if old_hash and new_hash == old_hash[0]:
            self._log(2, 'Func AddFile: file "%s" is IDENTICAL with the version stored in the '\
                'database!' % fname)
            return -1

        self.c.execute(('insert into %s (raw, hash, size, date, user) values (?,?,?,?,?)' % filename),
            [raw, new_hash, size, strftime("%Y-%b-%d %H:%M:%S"), os.getenv('USERNAME')])

        # If password is None, or password is False.
        if not password:
            self.c.execute('insert or ignore into _files_ (pwd, file) values (?,?)', [password, fname])
        # If password is provided by user, insert its hash in _files_ table.
        else:
            self.c.execute('insert or ignore into _files_ (pwd, file) values (?,?)', [pwd_hash, fname])

        # Set the labels...
        self.SetLabels(fname, labels)
        # File statistics...
        self.FileStatistics(fname)
        # Everything is fine, save.
        self.conn.commit()

        ver_max = self.c.execute('select version from %s order by version desc' % filename).fetchone()
        self._log(1, 'Adding file "%s", arch %s, version "%i" took %.4f sec.' % (filepath, arch, ver_max[0], clock()-ti))
        return 0


    def AddManyFiles(self, pathregex, password=1, labels='', versionable=True):
        '''
        Add more files, using a pattern. \n\
        If file doesn't exist in database, create the file. If file exists, add another row. \n\
        Versionable=False checks if the file is in the database. If it is, an error is raised
        and the file is not added. \n\
        '''
        ti = clock()
        path = os.path.split(pathregex)[0]

        if not os.path.exists(path):
            self._log(2, 'Func AddManyFiles: path "%s" doesn\'t exist!' % path)
            return -1

        pathreg = pathregex.replace('[', '[[]') # Fix possible bug in Windows ?
        files = glob.glob(pathreg)

        if not files:
            self._log(2, 'Func AddManyFiles: there are no files to match "%s"!' % pathregex)
            return -1

        for file in files:
            self.AddFile(file, password, labels, versionable)

        self._log(1, 'Added %i files in %.4f sec.' % (len(files), clock()-ti))
        return 0


    def CopyIntoNew(self, fname, version, new_fname):
        '''
        Copy one version of one file, into a new file, that will have version 1. \n\
        The password will be the same as in the original file. \n\
        '''
        ti = clock()
        if not validFileName(new_fname):
            self._log(2, 'Func CopyIntoNew: a file name cannot contain any of the following '\
                'characters  \\ / : * ? " < > |')
            return -1

        md4 = MD4.new(fname)
        filename = 't'+md4.hexdigest()
        del md4
        md4 = MD4.new(new_fname)
        new_filename = 't'+md4.hexdigest()
        del md4

        if version < 0 : version = 0

        # If new file name already exists, exit.
        if self.c.execute('select file from _files_ where file="%s"' % (new_fname)).fetchone():
            self._log(2, 'Func CopyIntoNew: there is already a file called "%s"!' % new_fname)
            return -1

        # Try to extract specified version.
        try:
            self.c.execute('select version from %s' % filename).fetchone()
        except:
            self._log(2, 'Func CopyIntoNew: there is no such file called "%s"!' % fname)
            return -1

        # If version was specified, get that version.
        if version:
            data = self.c.execute('select raw, hash, size from %s where version=%i' % \
                (filename, version)).fetchone()
        # Else, get the latest version.
        else:
            data = self.c.execute('select raw, hash, size from %s order by version desc' % \
                filename).fetchone()

        self.c.execute('create table %s (version integer primary key asc, raw BLOB, hash TEXT,'
            'size INTEGER, date TEXT, user TEXT)' % new_filename)
        self.c.execute(('insert into %s (raw, hash, size, date, user) values (?,?,?,?,?)' % new_filename),
            [data[0], data[1], data[2], strftime("%Y-%b-%d %H:%M:%S"), os.getenv('USERNAME')])

        # Use original password and labels of file.
        more = self.c.execute('select pwd, labels from _files_ where file=?', [fname]).fetchone()

        self.c.execute('insert into _files_ (file, pwd, labels) values (?,?,?)', (new_fname,)+more)
        self.FileStatistics(new_fname)
        self.conn.commit()

        self._log(1, 'Copying file "%s" into "%s" took %.4f sec.' % (fname, new_fname, clock()-ti))
        return 0


    def ExportFile(self, fname, password=1, version=0, path='', execute=False):
        '''
        Call one file from the briefcase. \n\
        If version is not null, that specific version is used. Else, the most recent version is used. \n\
        If execute is false, the file is simply exported into the specified path. Else, the file
        is executed from a temporary folder, or from the specified path, then the file is deleted. \n\
        '''
        ti = clock()
        md4 = MD4.new(fname)
        filename = 't'+md4.hexdigest()
        del md4

        if version < 0 : version = 0

        if path and not os.path.exists(path):
            self._log(2, 'Func ExportFile: path "%s" doesn\'t exist!' % path)
            return -1

        if not path and not execute:
            self._log(2, 'Func ExportFile: no path and no execute! The file will be generated and deleted immediately!')
            return -1

        # If version is a positive number, get that version.
        if version > 0:
            try:
                selected_version = self.c.execute('select raw, hash from %s where version=%s' % \
                    (filename, version)).fetchone()
            except:
                self._log(2, 'Func ExportFile: cannot find version "%i" for file "%s"!' % \
                    (version, fname))
                return -1
        # Else, get the latest version.
        else:
            try:
                selected_version = self.c.execute('select raw, hash from %s order by version desc' % \
                    filename).fetchone()
            except:
                self._log(2, 'Func ExportFile: cannot find the file called "%s"!' % fname)
                return -1

        # Get file password hash. It can be None, (Zero), or (some hash string).
        old_pwd_hash = self.c.execute('select pwd from _files_ where file="%s"' % fname).fetchone()

        if old_pwd_hash:
            old_pwd_hash = old_pwd_hash[0]

        # If password is a string or unicode, get the hash.
        if type(password) == type('') or type(password) == type(u''):
            pwd_hash = buffer(PBKDF2(password=password, salt='briefcase', dkLen=16, count=5000))
        # If password is database default, do nothing.
        elif password == 1:
            pwd_hash = 1
        # If password is null in some way, hash must be also null.
        else:
            password = None
            pwd_hash = None

        # If provided password != stored password...
        if old_pwd_hash != pwd_hash:
            self._log(2, 'Func ExportFile: Password for file "%s" is INCORRECT! You will not be '\
                'able to decrypt any data!' % fname)
            return -1

        # If the path is specified, use it
        if path:
            filename = path + '/' + fname
        # Else, create a temporary storage area
        else:
            # Create a temp dir
            tmpd = tempfile.mkdtemp('__', '__py')
            filename = tmpd + '/' + fname
            del tmpd

        w = open(filename, 'wb')
        w.write(self._restoreb(selected_version[0], password))
        w.close() ; del w
        self._log(1, 'Exporting file "%s" took %.4f sec.' % (fname, clock()-ti))

        if execute:
            # This function will call the file,
            # Then will overwrite the file,
            # Then will delete the temp folder, all threaded.
            # The Export Function here will not block.
            thread.start_new_thread(threaded_execute, (filename,),)

        # Return file hash.
        return selected_version[1]


    def ExportAll(self, path, password=1):
        '''
        Export all files into one folder. \n\
        Only the most recent version of each file is exported. \n\
        The files that don't use the global password, will fail to export. \n\
        '''
        #
        ti = clock()
        #
        if not os.path.exists(path):
            self._log(2, 'Func ExportAll: path "%s" doesn\'t exist!' % path)
            return -1

        # If password is a string or unicode, get the hash.
        if type(password) == type('') or type(password) == type(u''):
            pwd_hash = buffer(PBKDF2(password=password, salt='briefcase', dkLen=16, count=5000))
        # If password is database default, do nothing.
        elif password == 1:
            pwd_hash = 1
        # If password is null in some way, hash must be also null.
        else:
            password = None
            pwd_hash = None

        all_files = self.c.execute('select pwd, file from _files_ order by file').fetchall()

        # Temp_file[0] = pwd, Temp_file[1] = fname.
        for temp_file in all_files:
            # If provided password != stored password...
            if temp_file[0] != pwd_hash:
                self._log(2, 'Func ExportAll: Password for file "%s" is INCORRECT! You will not be'\
                    ' able to decrypt any data!' % temp_file[1])
                continue

            # At this point, password is correct.
            fname = path + '/' + temp_file[1]
            w = open(fname, 'wb')
            md4 = MD4.new(temp_file[1])
            filename = 't'+md4.hexdigest()
            latest_version = self.c.execute('select raw from %s order by version desc' % filename).fetchone()
            # Now write decompressed/ decrypted data.
            w.write(self._restoreb(latest_version[0], password))
            w.close()
            self._log(2, 'Func ExportAll: File "%s" exported successfully.' % temp_file[1])

        self._log(1, 'Exporting %i files took %.4f sec.' % (len(all_files), clock()-ti))
        return 0


    def Join(self, path1, **args):
        '''
        Joins two or more briefcase files. \n\
        All files from first briefcase file overwrite eventual duplicates from second briefcase,
        the resulted files overwrite eventual duplicates from third briefcase,
        the resulted files overwrite eventual duplicates from forth briefcase, etc,
        and the result is always stored in the last briefcase file, without changing the other briefcases. \n\
        If there are no duplicate files in the joining briefcases, all files will simply join, without any overwrite. \n\
        If one briefcase doesn't exist, it will be created, so you can join more briefcases into a new briefcase,
        without changing any other briefcase file. \n\
        '''
        #
        ti = clock()
        #

        #
        self._log(1, 'Joining databases took %.4f sec.' % clock()-ti)
        return 0


    def RenFile(self, fname, new_fname):
        '''
        Rename one file. This cannot be undone, so be careful! \n\
        '''
        ti = clock()
        if not validFileName(new_fname):
            self._log(2, 'Func RenFile: a filename cannot contain any of the following characters '\
                ' \\ / : * ? " < > |')
            return -1

        md4 = MD4.new(fname)
        filename = 't'+md4.hexdigest()
        del md4
        md4 = MD4.new(new_fname)
        new_filename = 't'+md4.hexdigest()
        del md4

        # Check file existence.
        if self.c.execute('select file from _files_ where file = ?', [new_fname]).fetchone():
            self._log(2, 'Func RenFile: there is already a file called "%s"!' % new_fname)
            return -1

        try:
            self.c.execute('alter table %s rename to %s' % (filename, new_filename))
            self.c.execute('update _files_ set file = ? where file = ?', [new_fname, fname])
            self.c.execute('update _statistics_ set file = ? where file = ?', [new_fname, fname])
            self.conn.commit()
            self._log(1, 'Renaming from "%s" into "%s" took %.4f sec.' % (fname, new_fname, clock()-ti))
            return 0
        except:
            self._log(2, 'Func RenFile: cannot find the file called "%s"!' % fname)
            return -1


    def DelFile(self, fname, version=0):
        '''
        If version is a positive number, only that version of the file is deleted. \n\
        Else, the entire table is dropped. \n\
        This cannot be undone, so be careful. \n\
        '''
        ti = clock()
        md4 = MD4.new(fname)
        filename = 't'+md4.hexdigest()
        del md4

        if version > 0:
            self.c.execute('delete from %s where version=%s' % (filename, version))
            self.c.execute('reindex %s' % filename)
            self.conn.commit()
            self._log(1, 'Deleting file "%s" version "%i" took %.4f sec.' % (fname, version, clock()-ti))
            return 0
        else:
            try:
                self.c.execute('drop table %s' % filename)
                self.c.execute('delete from _files_ where file="%s"' % fname)
                self.c.execute('delete from _statistics_ where file="%s"' % fname)
                self.conn.commit()
                self._log(1, 'Deleting file "%s" took %.4f sec.' % (fname, clock()-ti))
                return 0
            except:
                self._log(2, 'Func DelFile: cannot find the file called "%s"!' % fname)
                return -1


    def FileStatistics(self, fname, silent=True):
        '''
        Generate/ return a dictionary containing the following key-value pairs : \n\
        fileName, firstSize, lastSize, firstFileDate, lastFileDate, biggestSize,
        firstFileUser, lastFileUser, fileLabels, versions. \n\
        If the file has 1 version, firstSize==lastSize and firstFileDate==lastFileDate and
        firstFileUser==lastFileUser. \n\
        On error, it returns an empty dictionary. \n\
        '''
        ti = clock()
        md4 = MD4.new(fname)
        filename = 't'+md4.hexdigest()
        del md4

        # Check file existence.
        if not self.c.execute('select file from _files_ where file = ?', [fname]).fetchone():
            self._log(2, 'Func FileStatistics: there is no such file called "%s"!' % fname)
            return {}

        # Size.
        biggestSize = self.c.execute('select size from %s order by size desc' %
            filename).fetchone()[0]
        firstFileSize = self.c.execute('select size from %s order by version asc' %
            filename).fetchone()[0]
        lastFileSize = self.c.execute('select size from %s order by version desc' %
            filename).fetchone()[0]
        # Date added.
        firstFileDate = self.c.execute('select date from %s order by version asc' %
            filename).fetchone()[0]
        lastFileDate = self.c.execute('select date from %s order by version desc' %
            filename).fetchone()[0]
        # User added.
        firstFileUser = self.c.execute('select user from %s order by version asc' %
            filename).fetchone()[0]
        lastFileUser = self.c.execute('select user from %s order by version desc' %
            filename).fetchone()[0]
        labels = self.c.execute('select labels from _files_ where file="%s"' %
            fname).fetchone()[0]
        versions = len( self.c.execute('select version from %s' % filename).fetchall() )

        self.c.execute('insert or replace into _statistics_ (file, size0, size, sizeB, '
            'date0, date, user0, user, labels) values (?,?,?,?,?,?,?,?,?)', [fname,
            firstFileSize, lastFileSize, biggestSize, firstFileDate, lastFileDate,
            firstFileUser, lastFileUser, labels])

        if not silent:
            self._log(1, 'Get properties for file "%s" took %.4f sec.' % (fname, clock()-ti))
        return {'fileName':fname, 'internFileName':filename, 'biggestSize':biggestSize,
            'firstFileSize':firstFileSize, 'lastFileSize':lastFileSize,
            'firstFileDate':firstFileDate, 'lastFileDate':lastFileDate,
            'firstFileUser':firstFileUser, 'lastFileUser':lastFileUser,
            'labels':labels, 'versions':versions}


    def GetFileList(self, ssort='', ffilter=''):
        '''
        Returns a list with all the files from current Briefcase file. \n\
        Can sort/ filter after file name, size, date added. \n\
        Labels and user name can only be used as ffilter. \n\
        On error, it returns -1. \n\
        '''
        ti = clock()

        if (not ssort) and (not ffilter):
            vList = self.c.execute('select file from _files_ order by file asc').fetchall()
            self._log(1, 'Get file list took %.4f sec.' % (clock()-ti))
            return [vElem[0] for vElem in vList]

        # Validate sort expression.
        if ssort and ssort.lower() not in ['file asc', 'file desc', 'size0 asc', 'size0 desc',
            'size asc', 'size desc', 'sizeb asc', 'sizeb desc',
            'date0 asc', 'date0 desc', 'date asc', 'date desc']:
            self._log(2, 'Func GetFileList: sort "%s" is incorrect!' % ssort)
            return -1
        # Validate filter expression.
        if ffilter and not re.match('(file|labels|size0|size|sizeb|date0|date|user0|user)[ ]*',
            ffilter.lower()):
            self._log(2, 'Func GetFileList: filter "%s" is incorrect!' % ffilter)
            return -1

        if ssort:
            ssort = 'order by ' + ssort
        if ffilter:
            ffilter = 'where ' + ffilter

        try:
            vList = self.c.execute('select file from _statistics_ %s %s' % (ffilter, ssort)).fetchall()
        except:
            self._log(2, 'Func GetFileList: sql expression "%s %s" incorrect in context!' % (ffilter, ssort))
            return -1

        self._log(1, 'Get file list took %.4f sec.' % (clock()-ti))
        return [vElem[0] for vElem in vList]


    def GetLabelsList(self):
        '''
        Returns a list with all the labels from current Briefcase file. \n\
        Cannot have errors. \n\
        '''
        ti = clock()
        vList = self.c.execute('select distinct labels from _files_').fetchall()
        vFinal = [vElem[0] for vElem in vList]
        vList = ';'.join(vFinal)
        vFinal = vList.split(';')
        vList = sorted(list(set(vFinal)))
        if str(vList[0]) == '':
            del vList[0]
        self._log(1, 'Get labels list took %.4f sec.' % (clock()-ti))
        return vList


    def Info(self):
        '''
        Returns a dictionary containing the following information for this Briefcase file : \n\
        - number of files \n\
        - date created \n\
        - user that created it \n\
        - all labels used \n\
        - version of program used to create the file. \n\
        Cannot have errors. \n\
        '''
        ti = clock()
        li = self.c.execute('select file from _files_').fetchall()
        numberOfFiles = len(li) ; del li
        dateCreated = self.c.execute('select date from _info_').fetchone()[0]
        userCreated = self.c.execute('select user from _info_').fetchone()[0]
        allLabels = ', '.join(self.GetLabelsList())
        versionCreated = self.c.execute('select version from _info_').fetchone()[0]

        self._log(1, 'Get database info took %.4f sec.' % (clock()-ti))
        return {'numberOfFiles':numberOfFiles, 'dateCreated':dateCreated , 'userCreated':userCreated,
            'allLabels':allLabels, 'versionCreated':versionCreated}


    def Cleanup(self):
        '''
        Deletes table _statistics_. \n\
        Cleans the main database by copying its contents to a temporary database file and
        reloading the original database file from the copy. \n\
        This eliminates free pages, aligns table data to be contiguous, and otherwise
        cleans up the database file structure. \n\
        '''
        ti = clock()

        global EXEC_statistics_, EXEC_logs_
        self.c.execute('drop table _statistics_') # Delete table _statistics_.
        self.c.execute(EXEC_statistics_.replace(' if not exists', ''))

        self.c.execute('drop table _logs_') # Delete table _logs_.
        self.c.execute(EXEC_logs_.replace(' if not exists', ''))

        # Rebuilding statistics.
        for fname in self.c.execute('select file from _files_ order by file asc').fetchall():
            self.FileStatistics(fname[0])

        self.c.execute('VACUUM')
        self._log(1, 'Cleanup took %.4f sec.' % (clock()-ti))


#


if __name__ == '__main__':

    '''
    This is a work in progress...
    '''

    if not sys.argv[3:]:
        print('You must specify 3 arguments. Try "-h" parameter to see the complete list of commands.')
        exit(1)

    from optparse import OptionParser
    usage = "Usage: %prog --db <briefcase-file> --pwd <password> --command <arguments>"
    parser = OptionParser(usage=usage)

    parser.add_option("-b", "-q", "--brief", "--quiet", dest="verbose", action="store_false", default=False, help="Prints the version.")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=True, help="Prints the version.")
    parser.add_option("--db", "--file", dest="database", help="The name of the briefcase file.")
    parser.add_option("--pwd", "--pass", dest="password", help="The password of the briefcase file.")

    parser.add_option("--addfile", action="store", nargs=2, help="-.")
    parser.add_option("--addmanyfiles", action="store", nargs=2, help="-.")
    parser.add_option("--copyintonew", action="store", nargs=3, help="-.")
    parser.add_option("--exportfile", action="store", nargs=4, help="-.")
    parser.add_option("--exportall", action="store", nargs=1, help="-.")
    parser.add_option("--renfile", action="store", nargs=2, help="-.")
    parser.add_option("--delfile", action="store", nargs=2, help="-.")
    (options, args) = parser.parse_args()

    print( options )


# Eof()
