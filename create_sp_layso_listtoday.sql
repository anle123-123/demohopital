
IF OBJECT_ID('dbo.sp_LaySo_ListToday', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_LaySo_ListToday;
GO

CREATE PROCEDURE dbo.sp_LaySo_ListToday
    @Khoa NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Indices expected by app.py:
    -- 0: ID
    -- 1: KHOA
    -- 2: SO_THU_TU
    -- 3: HOVATEN
    -- 4: STATUS
    -- 5: CREATED_AT
    SELECT 
        ID,
        KHOA,
        SO_THU_TU,
        HOVATEN,
        STATUS,
        CREATED_AT
    FROM dbo.LAYSO_ONLINE
    WHERE CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)
      AND (@Khoa IS NULL OR KHOA = @Khoa)
    ORDER BY SO_THU_TU ASC;
END;
GO
