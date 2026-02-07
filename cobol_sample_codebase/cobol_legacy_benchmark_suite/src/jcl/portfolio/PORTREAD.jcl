//******************************************************************
//* JCL Name: PORTREAD
//* Description: Execute Portfolio Reading Program
//* Author: [Author name]
//* Date Written: 2024-03-20
//******************************************************************
//PORTREAD  JOB (ACCT),'READ PORTFOLIO',
//          CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//STEP1    EXEC PGM=PORTREAD
//STEPLIB   DD DSN=YOUR.LOADLIB,DISP=SHR
//PORTFILE  DD DSN=PORTFOLIO.MASTER.FILE,DISP=SHR
//SYSOUT    DD SYSOUT=*
//SYSPRINT  DD SYSOUT=*
//SYSUDUMP  DD SYSOUT=* 