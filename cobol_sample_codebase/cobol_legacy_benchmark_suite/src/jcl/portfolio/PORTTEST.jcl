//******************************************************************
//* JCL Name: PORTTEST
//* Description: Generate Portfolio Test Data
//* Author: [Author name]
//* Date Written: 2024-03-20
//******************************************************************
//PORTTEST  JOB (ACCT),'GEN TEST DATA',
//          CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//STEP1    EXEC PGM=PORTTEST
//STEPLIB   DD DSN=YOUR.LOADLIB,DISP=SHR
//TESTFILE  DD DSN=PORTFOLIO.TEST.FILE,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(1,1)),
//             DCB=(RECFM=FB,LRECL=200,BLKSIZE=0)
//SYSOUT    DD SYSOUT=*
//SYSPRINT  DD SYSOUT=*
//SYSUDUMP  DD SYSOUT=* 