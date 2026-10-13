-- Runs once, when the PostgreSQL volume is first initialised.
-- Tests use their own database so they never touch development data.
CREATE DATABASE expenses_test;
