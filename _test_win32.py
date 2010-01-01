#! /usr/local/bin/python
# -*- coding: latin-1 -*-

from glob import glob
from briefcase import Briefcase

# Creating Briefcase instance.
b = Briefcase('Data.prv', '0123456789abcQW')

# Adding a few files.
ret = b.AddManyFiles(r'c:\WINDOWS\Web\Wallpaper\*.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Add another file.
ret = b.AddFile('readme.txt')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Add identical file.
ret = b.AddFile('readme.txt')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Rename.
ret = b.RenFile('bliss.jpg', 'to_delete.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Properties.
ret = b.GetProperties('to_delete.jpg')
if ret!=-1 : print( ret )
else : print( b.lastErrorMsg )

# Copy.
ret = b.CopyIntoNew('to_delete.jpg', 1, 'to_execute.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Copy again, just to make sure. :)
ret = b.CopyIntoNew('to_execute.jpg', 1, 'to_delete2.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Delete.
ret = b.DelFile('to_delete.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Delete error.
ret = b.DelFile('to_delete.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Delete again.
ret = b.DelFile('to_delete2.jpg')
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

# Execute.
ret = b.ExportFile('to_execute.jpg', path='d:', execute=False)
if not ret : print( b.lastDebugMsg )
else : print( b.lastErrorMsg )

print( 'Done !' )

# Eof()