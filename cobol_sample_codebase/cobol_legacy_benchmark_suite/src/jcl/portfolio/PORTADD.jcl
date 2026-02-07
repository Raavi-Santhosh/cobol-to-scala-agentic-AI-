//******************************************************************
//* JCL Name: PORTADD
//* Description: Execute Portfolio Addition Program
//* Author: [Author name]
//* Date Written: 2024-03-20
//******************************************************************
//PORTADD   JOB (ACCT),'ADD PORTFOLIO',
//          CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//STEP1    EXEC PGM=PORTADD
//STEPLIB   DD DSN=YOUR.LOADLIB,DISP=SHR
//PORTFILE  DD DSN=PORTFOLIO.MASTER.FILE,DISP=SHR
//INPTFILE  DD DSN=PORTFOLIO.INPUT.FILE,DISP=OLD
//SYSOUT    DD SYSOUT=*
//SYSPRINT  DD SYSOUT=*
//SYSUDUMP  DD SYSOUT=* 