//******************************************************************
//* JCL Name: PORTDEL
//* Description: Execute Portfolio Deletion Program
//* Author: [Author name]
//* Date Written: 2024-03-20
//******************************************************************
//PORTDEL   JOB (ACCT),'DELETE PORTFOLIO',
//          CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//STEP1    EXEC PGM=PORTDEL
//STEPLIB   DD DSN=YOUR.LOADLIB,DISP=SHR
//PORTFILE  DD DSN=PORTFOLIO.MASTER.FILE,DISP=SHR
//DELEFILE  DD DSN=PORTFOLIO.DELETE.FILE,DISP=OLD
//AUDFILE   DD DSN=PORTFOLIO.AUDIT.FILE,DISP=MOD
//SYSOUT    DD SYSOUT=*
//SYSPRINT  DD SYSOUT=*
//SYSUDUMP  DD SYSOUT=* 