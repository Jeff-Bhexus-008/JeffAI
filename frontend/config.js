/*
 * JeffAI bundled Supabase configuration.
 *
 * The backend serves the authoritative project at /api/config, so a
 * project migration only needs new SUPABASE_URL / SUPABASE_KEY values
 * on the server (Render) - nothing to rebuild here.
 *
 * These values are the offline/native fallback, used only when the API
 * cannot be reached (for example the Android shell with no network).
 * Keep them pointing at the same live project as the server.
 */

const SUPABASE_URL = "https://enpcfbebqwcsrrvvghev.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVucGNmYmVicXdjc3JydnZnaGV2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODg5Mzg3NTEsImV4cCI6MjEwNDUxNDc1MX0.A8WPSQ2ZbsUxs33GTTLvUNMuwUcHOTSHTd0U-7VjqJA";

// Also exposed on window so module scripts can read them.
window.SUPABASE_URL = SUPABASE_URL;
window.SUPABASE_ANON_KEY = SUPABASE_ANON_KEY;
