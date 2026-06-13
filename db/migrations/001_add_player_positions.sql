-- Migration 001: eligible defensive positions per player.
-- Run this once in the Supabase SQL Editor on an existing database.
-- (New installs get this column directly from schema.sql.)

alter table players add column if not exists positions text[];
