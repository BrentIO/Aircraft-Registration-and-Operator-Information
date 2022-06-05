/* Add the 'source' column to operators */

SELECT IF (
    EXISTS (
        SELECT DISTINCT column_name FROM information_schema.columns WHERE TABLE_NAME = 'operators' AND COLUMN_NAME = 'source' )
		, 'EXISTS'
		, 'NOT_EXISTS') into @columnTest;
               
SELECT IF ( @columnTest = 'NOT_EXISTS',
	'ALTER TABLE operators ADD COLUMN source INT NOT NULL AFTER hash;',
	'SELECT ''Operators Already Contains Source Column; Ignoring''') into @actionCommand;

PREPARE stmtCreateColumn FROM @actionCommand;
EXECUTE stmtCreateColumn;
DEALLOCATE PREPARE stmtCreateColumn;

SELECT IF ( @columnTest = 'NOT_EXISTS',
'UPDATE operators SET source = (SELECT unique_id FROM sources where agency = ''Mictronics-IndexedDB'') WHERE source = 0;',
'SELECT ''Operator Source Already Set; Ignoring''') into @actionCommand;

PREPARE stmtUpdateData FROM @actionCommand;
EXECUTE stmtUpdateData;
DEALLOCATE PREPARE stmtUpdateData;

