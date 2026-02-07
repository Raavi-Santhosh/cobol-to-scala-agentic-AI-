*****************************************************************
* CICS Resource Definitions for Portfolio System                  *
*****************************************************************

* Transaction Definitions
DEFINE TRANSACTION(PINQ)
       PROGRAM(INQONLN)
       PROFILE(DFHCICST)
       DESCRIPTION(Portfolio Inquiry Transaction)
       GROUP(PORTGRP)
       STATUS(ENABLED)

* Program Definitions
DEFINE PROGRAM(INQONLN)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

DEFINE PROGRAM(INQPORT)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

DEFINE PROGRAM(INQHIST)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

DEFINE PROGRAM(DB2ONLN)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

DEFINE PROGRAM(CURSMGR)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

DEFINE PROGRAM(DB2RECV)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

DEFINE PROGRAM(SECMGR)
       LANGUAGE(COBOL)
       DATALOCATION(ANY)
       EXECKEY(USER)
       RESIDENT(NO)
       GROUP(PORTGRP)

* Mapset Definition
DEFINE MAPSET(INQSET)
       RESIDENT(NO)
       GROUP(PORTGRP)

* File Definitions
DEFINE FILE(POSFILE)
       DSNAME(PORTFOLIO.POSITION.VSAM)
       GROUP(PORTGRP)
       ADD(YES)
       BROWSE(YES)
       DELETE(NO)
       READ(YES)
       UPDATE(NO)
       RECORDSIZE(200)
       STRINGS(10)
       STATUS(ENABLED)

* DB2ENTRY Definitions
DEFINE DB2ENTRY(PORTDB2)
       ACCOUNTREC(NONE)
       AUTHTYPE(USERID)
       PLAN(PORTPLAN)
       PRIORITY(HIGH)
       PROTECTNUM(5)
       GROUP(PORTGRP)

* DB2TRAN Definition
DEFINE DB2TRAN(PINQ)
       ENTRY(PORTDB2)
       TRANSID(PINQ)
       GROUP(PORTGRP)

* Group List
DEFINE LIST(PORTLST)
       DESCRIPTION(Portfolio System Group List)
       GROUP(PORTGRP)
       STATUS(ENABLED) 