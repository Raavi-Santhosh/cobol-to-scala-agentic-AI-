//******************************************************************
//* JCL Name: PORTUPDT
//* Description: Execute Portfolio Update Program
//* Author: [Author name]
//* Date Written: 2024-03-20
//******************************************************************
//PORTUPDT  JOB (ACCT),'UPDATE PORTFOLIO',
//          CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//STEP1    EXEC PGM=PORTUPDT
//STEPLIB   DD DSN=YOUR.LOADLIB,DISP=SHR
//PORTFILE  DD DSN=PORTFOLIO.MASTER.FILE,DISP=SHR
//UPDTFILE  DD DSN=PORTFOLIO.UPDATE.FILE,DISP=OLD
//SYSOUT    DD SYSOUT=*
//SYSPRINT  DD SYSOUT=*
//SYSUDUMP  DD SYSOUT=* 