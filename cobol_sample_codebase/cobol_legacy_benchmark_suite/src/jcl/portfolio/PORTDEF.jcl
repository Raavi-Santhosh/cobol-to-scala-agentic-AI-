//******************************************************************
//* JCL Name: PORTDEF
//* Description: Define Portfolio Master VSAM File
//* Author: [Author name]
//* Date Written: 2024-03-20
//*
//* Maintenance Log:
//* Date       Author        Description
//* ---------- ------------- -------------------------------------
//* 2024-03-20 [Author]     Initial Creation
//******************************************************************
//PORTDEF   JOB (ACCT),'DEFINE PORTFOLIO',
//          CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//******************************************************************
//* Delete existing VSAM file if it exists
//******************************************************************
//DEFVSAM   EXEC PGM=IDCAMS
//SYSPRINT  DD SYSOUT=*
//SYSIN     DD *
  DELETE PORTFOLIO.MASTER.FILE CLUSTER
  SET MAXCC = 0
//*
//******************************************************************
//* Define new VSAM file
//******************************************************************
  DEFINE CLUSTER (NAME(PORTFOLIO.MASTER.FILE) -
         INDEXED -
         RECORDSIZE(200 200) -
         KEYS(18 0) -
         CYLINDERS(5 1) -
         FREESPACE(10 10) -
         SHAREOPTIONS(2 3))