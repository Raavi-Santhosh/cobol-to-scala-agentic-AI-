       01  WS-RECORD.
           05  WS-RECORD-ID          PIC X(10).
           05  WS-RECORD-AMOUNT      PIC 9(10).
           05  WS-RECORD-DATE        PIC X(10).
           05  WS-RECORD-STATUS      PIC X(1).
               88  WS-STATUS-VALID   VALUE 'Y'.
               88  WS-STATUS-INVALID VALUE 'N'.
