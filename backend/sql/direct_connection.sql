-- 获取直接 PostgreSQL 连接信息
-- 在 Supabase Dashboard → Database → Connection String 中找到

-- 测试直接连接是否可用
SELECT 'Direct connection works' as status;

-- 显示所有表
SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'club_%';
