/* Utils.em - a small collection of useful editing macros */



/*-------------------------------------------------------------------------
	I N S E R T   H E A D E R

	Inserts a comment header block at the top of the current function.
	This actually works on any type of symbol, not just functions.

	To use this, define an environment variable "MYNAME" and set it
	to your email name.  eg. set MYNAME=raygr
-------------------------------------------------------------------------*/
macro InsertHeader()
{
	// Get the owner's name from the environment variable: MYNAME.
	// If the variable doesn't exist, then the owner field is skipped.
	szMyName = getenv(MYNAME)

	// Get a handle to the current file buffer and the name
	// and location of the current symbol where the cursor is.
	hbuf = GetCurrentBuf()
	szFunc = GetCurSymbol()
	ln = GetSymbolLine(szFunc)

	// begin assembling the title string
	sz = "/*   "

	/* convert symbol name to T E X T   L I K E   T H I S */
	cch = strlen(szFunc)
	ich = 0
	while (ich < cch)
		{
		ch = szFunc[ich]
		if (ich > 0)
			if (isupper(ch))
				sz = cat(sz, "   ")
			else
				sz = cat(sz, " ")
		sz = Cat(sz, toupper(ch))
		ich = ich + 1
		}

	sz = Cat(sz, "   */")
	InsBufLine(hbuf, ln, sz)
	InsBufLine(hbuf, ln+1, "/*-------------------------------------------------------------------------")

	/* if owner variable exists, insert Owner: name */
	if (strlen(szMyName) > 0)
		{
		InsBufLine(hbuf, ln+2, "    Owner: @szMyName@")
		InsBufLine(hbuf, ln+3, " ")
		ln = ln + 4
		}
	else
		ln = ln + 2

	InsBufLine(hbuf, ln,   "    ") // provide an indent already
	InsBufLine(hbuf, ln+1, "-------------------------------------------------------------------------*/")

	// put the insertion point inside the header comment
	SetBufIns(hbuf, ln, 4)
}


/* InsertFileHeader:

   Inserts a comment header block at the top of the current function.
   This actually works on any type of symbol, not just functions.

   To use this, define an environment variable "MYNAME" and set it
   to your email name.  eg. set MYNAME=raygr
*/

macro InsertFileHeader()
{
	szMyName = getenv(MYNAME)

	hbuf = GetCurrentBuf()

	InsBufLine(hbuf, 0, "/*-------------------------------------------------------------------------")

	/* if owner variable exists, insert Owner: name */
	InsBufLine(hbuf, 1, "    ")
	if (strlen(szMyName) > 0)
		{
		sz = "    Owner: @szMyName@"
		InsBufLine(hbuf, 2, " ")
		InsBufLine(hbuf, 3, sz)
		ln = 4
		}
	else
		ln = 2

	InsBufLine(hbuf, ln, "-------------------------------------------------------------------------*/")
}



// Inserts "Returns True .. or False..." at the current line
macro ReturnTrueOrFalse()
{
	hbuf = GetCurrentBuf()
	ln = GetBufLineCur(hbuf)

	InsBufLine(hbuf, ln, "    Returns True if successful or False if errors.")
}



/* Inserts ifdef REVIEW around the selection */
macro IfdefReview()
{
	IfdefSz("REVIEW");
}


/* Inserts ifdef BOGUS around the selection */
macro IfdefBogus()
{
	IfdefSz("BOGUS");
}


/* Inserts ifdef NEVER around the selection */
macro IfdefNever()
{
	IfdefSz("NEVER");
}


// Ask user for ifdef condition and wrap it around current
// selection.
macro InsertIfdef()
{
	sz = Ask("Enter ifdef condition:")
	if (sz != "")
		IfdefSz(sz);
}

macro InsertCPlusPlus()
{
	IfdefSz("__cplusplus");
}


// Wrap ifdef <sz> .. endif around the current selection
macro IfdefSz(sz)
{
	hwnd = GetCurrentWnd()
	lnFirst = GetWndSelLnFirst(hwnd)
	lnLast = GetWndSelLnLast(hwnd)

	hbuf = GetCurrentBuf()
	InsBufLine(hbuf, lnFirst, "#ifdef @sz@")
	InsBufLine(hbuf, lnLast+2, "#endif /* @sz@ */")
}


// Delete the current line and appends it to the clipboard buffer
macro KillLine()
{
	hbufCur = GetCurrentBuf();
	lnCur = GetBufLnCur(hbufCur)
	hbufClip = GetBufHandle("Clipboard")
	AppendBufLine(hbufClip, GetBufLine(hbufCur, lnCur))
	DelBufLine(hbufCur, lnCur)
}


// Paste lines killed with KillLine (clipboard is emptied)
macro PasteKillLine()
{
	Paste
	EmptyBuf(GetBufHandle("Clipboard"))
}



// delete all lines in the buffer
macro EmptyBuf(hbuf)
{
	lnMax = GetBufLineCount(hbuf)
	while (lnMax > 0)
		{
		DelBufLine(hbuf, 0)
		lnMax = lnMax - 1
		}
}


// Ask the user for a symbol name, then jump to its declaration
macro JumpAnywhere()
{
	symbol = Ask("What declaration would you like to see?")
	JumpToSymbolDef(symbol)
}


// list all siblings of a user specified symbol
// A sibling is any other symbol declared in the same file.
macro OutputSiblingSymbols()
{
	symbol = Ask("What symbol would you like to list siblings for?")
	hbuf = ListAllSiblings(symbol)
	SetCurrentBuf(hbuf)
}


// Given a symbol name, open the file its declared in and
// create a new output buffer listing all of the symbols declared
// in that file.  Returns the new buffer handle.
macro ListAllSiblings(symbol)
{
	loc = GetSymbolLocation(symbol)
	if (loc == "")
		{
		msg ("@symbol@ not found.")
		stop
		}

	hbufOutput = NewBuf("Results")

	hbuf = OpenBuf(loc.file)
	if (hbuf == 0)
		{
		msg ("Can't open file.")
		stop
		}

	isymMax = GetBufSymCount(hbuf)
	isym = 0;
	while (isym < isymMax)
		{
		AppendBufLine(hbufOutput, GetBufSymName(hbuf, isym))
		isym = isym + 1
		}

	CloseBuf(hbuf)

	return hbufOutput

}

/* added personally */
macro FilterNrWithoutUt()
{
	search_pattern = "nr_fw_app_l0"
	remove_pattern = "unittest"

	FilterTextRegex(search_pattern, remove_pattern)

	remove_pattern_2 = "comptest"
	FilterTextRegex("", remove_pattern_2)
}

macro FilterTextWithRemove()
{
	search_pattern = Ask("Search pattern (regex):")
	remove_pattern = Ask("Remove pattern (regex):")

	if (search_pattern == " ")
	{
		search_pattern = ""
	}

	if (remove_pattern == " ")
	{
		remove_pattern = ""
	}

	FilterTextRegex(search_pattern, remove_pattern)
}

macro FilterText()
{
	search_pattern = Ask("Search pattern (regex):")
	remove_pattern = ""

	FilterTextRegex(search_pattern, remove_pattern)
}

macro PatternInBufLine(pattern, buf, line)
{
	search_result = SearchInBuf(buf, pattern, line, 0, 0, 1, 0)
	if (search_result != "")
	{
		if ( search_result.lnFirst == line)
		{
			return 1
		}
	}
	return 0
}

macro GetBufLastLineAndDel(buf)
{
	line_count = GetBufLineCount(buf)
	if (line_count == 0)
	{
		return -1
	}
	else
	{
		last_line = GetBufLine(buf, line_count - 1)
		DelBufLine(buf, line_count - 1)
		//Msg(last_line)
	}
	return last_line
}

macro FilterTextRegex(search_pattern, remove_pattern)
{
	hBuf = GetCurrentBuf()
	hWnd = GetCurrentWnd()

	line_count = GetBufLineCount(hBuf)
	hLinebuf = NewBuf("temp")
	ClearBuf(hLinebuf)

	ln = 1
	while (ln < line_count)
	{
		ln_saved = 1
		if (search_pattern != "")
		{
			if (!PatternInBufLine(search_pattern, hBuf, ln))
			{
				ln_saved = 0
			}
		}

		if (ln_saved == 1)
		{
			if (remove_pattern != "")
			{
				if (PatternInBufLine(remove_pattern, hBuf, ln))
				{
					ln_saved = 0
				}
			}
		}

		if (ln_saved == 1)
		{
			AppendBufLine(hLinebuf, ln)
			//Msg(ln)
		}
		ln = ln + 1
	}

	last_line = GetBufLastLineAndDel(hLinebuf)

	ln = line_count - 1
	while (ln >= 1)
	{
		if (ln == last_line)
		{
			last_line = GetBufLastLineAndDel(hLinebuf)
		}
		else
		{
			DelBufLine(hBuf, ln)
		}
		ln = ln -1
	}

	CloseBuf(hLinebuf)
}

macro OpenFileFolder()
{
	hBuf = GetCurrentBuf()
	file_path = GetBufName(hBuf)
	RunCmdLine("explorer.exe /select,@file_path@", Nil, 0);
}

macro BackFindCharInStr(str, c)
{
	len = strlen(str)
	pos = -1

	while (len > 0)
	{
		len = len - 1
		if (strmid(str, len, len+1) == c)
		{
			pos = len
			break
		}
	}
	return pos
}

macro BackFindCharInStrMulti(str, c, times)
{
	pos = -1
	while (times > 0)
	{
		pos = BackFindCharInStr(str, c)
		if (pos < 0) break
		str = strmid(str, 0, pos)
		times = times - 1
	}
	return pos
}

macro SwitchCppAndHpp()
{
	hBuf = GetCurrentBuf()
	abs_file_name = GetBufName(hBuf)

	len = strlen(abs_file_name)
	pos = BackFindCharInStr(abs_file_name, ".")
	if ((pos < 0) || (pos >= (len-1))) stop

	file_ext = strmid(abs_file_name, pos+1, len)
	if (tolower(file_ext) == "cpp")
	{
		open_file_ext = "hpp"
	}
	else if (tolower(file_ext) == "hpp")
	{
		open_file_ext = "cpp"
	}
	else if (tolower(file_ext) == "c")
	{
		open_file_ext = "h"
	}
	else if (tolower(file_ext) == "h")
	{
		open_file_ext = "c"
	}
	else
	{
		stop
	}

	folder_1_pos = BackFindCharInStr(abs_file_name, "\\")
	folder_2_pos = BackFindCharInStrMulti(abs_file_name, "\\", 2)
	if ((folder_1_pos < 0) || (folder_2_pos < 0)) stop

	file_name = strmid(abs_file_name, folder_1_pos+1, pos)
	folder = strmid(abs_file_name, 0, folder_2_pos)
	//Msg(file_name)
	//Msg(folder)

	if (open_file_ext == "cpp")
	{
		target_file = cat(cat(folder, "\\code\\"), cat(file_name, ".cpp"))
		target_file_1 = ""
	}
	else if(open_file_ext == "hpp")
	{
		target_file = cat(cat(folder, "\\include\\"), cat(file_name, ".hpp"))
		target_file_1 = cat(cat(folder, "\\interface\\"), cat(file_name, ".hpp"))
		//Msg(target_file_1)
	}
	else if(open_file_ext == "c")
	{
		target_file = cat(cat(folder, "\\code\\"), cat(file_name, ".c"))
		target_file_1 = ""
	}
	else if(open_file_ext == "h")
	{
		target_file = cat(cat(folder, "\\include\\"), cat(file_name, ".h"))
		target_file_1 = cat(cat(folder, "\\interface\\"), cat(file_name, ".h"))
		//Msg(target_file_1)
	}
	//Msg(target_file)

	hTargetBuf = OpenBuf(target_file)
	if(hTargetBuf != hNil)
	{
		SetCurrentBuf(hTargetBuf)
		stop
	}
	if (target_file_1 != "")
	{
		hTargetBuf = OpenBuf(target_file_1)
		if(hTargetBuf != hNil)
		{
			SetCurrentBuf(hTargetBuf)
			stop
		}
	}
}


