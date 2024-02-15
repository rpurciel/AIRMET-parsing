class StatementObj():
'''A "Statement" = A group of 
   MET Info objects issued at 
   the same time.

   e.g. A SIGMET with multiple 
   areas, issued at the same
   time.

   Contains subclasses:
   - n MetInfoObjs
'''
	def __init__(self):
		pass

class MetInfoObj():
''' A "MET Info" object = A
	single product issued
	covering defined bounds.

	Inherits attributes:
	- Type of MET Info
	- Valid From Time
	- Valid To Time

	Contains attributes:
	- Type of Warning
	- Raw Description
	- Other Info

	Contains subclasses:
	- Conditions & Parsed Description
	- Bounds
	- States

'''

	def __init__(self):
		pass

