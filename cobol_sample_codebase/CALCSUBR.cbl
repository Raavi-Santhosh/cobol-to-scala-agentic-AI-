       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALCSUBR.
       AUTHOR. SYSTEM.
       
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CALCDATA.
       
       LINKAGE SECTION.
       COPY WORKAREA.
       
       COPY MISSINGCOPY.
       
       PROCEDURE DIVISION USING WS-RECORD.
       MAIN-CALC.
           COMPUTE WS-CALC-VALUE = 
               WS-RECORD-AMOUNT * WS-MULTIPLIER.
           
           IF WS-RECORD-STATUS = 'Y'
               ADD WS-EXTRA-VALUE TO WS-CALC-VALUE
           END-IF.
           
           GOBACK.
