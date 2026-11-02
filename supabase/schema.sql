-- =========================================================
-- JeffAI schema additions
-- Created by Amedu Vincent Onjefu (Jeff Bhexus)
--
-- Run this in the Supabase SQL editor. It is safe to run more than
-- once: it only adds the image gallery table that the Image Studio
-- uses to keep generated images in "Saved files".
--
-- Existing tables used by JeffAI and left untouched:
--   conversations (id, user_id, title, created_at, updated_at)
--   messages      (id, conversation_id, user_id, role, content, created_at)
--   memories      (id, user_id, memory, created_at)
--   documents     (id, user_id, filename, file_path, file_type,
--                  extracted_text, created_at)
-- =========================================================

create table if not exists public.images (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    prompt text not null default '',
    file_path text not null,
    file_type text not null default 'png',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists images_user_created_idx
    on public.images (user_id, created_at desc);

alter table public.images enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'images'
          and policyname = 'images belong to their owner'
    ) then
        create policy "images belong to their owner"
            on public.images
            for all
            using (auth.uid() = user_id)
            with check (auth.uid() = user_id);
    end if;
end $$;

grant select, insert, update, delete on public.images to authenticated;


-- =========================================================
-- STORAGE
-- =========================================================
--
-- Generated images are stored in the existing "documents" bucket under
--   images/<user_id>/<uuid>.png
-- so the same bucket policies that already allow document uploads and
-- downloads cover them too. If you would rather keep images separate:
--
--   1. Create a private bucket called "images".
--   2. Point IMAGE_BUCKET at it in the backend (see backend/ai/images.py).
--   3. Add owner-scoped policies on storage.objects for that bucket.
--
-- Signed URLs are generated server side, so the bucket stays private.
