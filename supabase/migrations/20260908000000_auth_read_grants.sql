-- MVP-04: RLS filtra filas, pero no concede el privilegio SQL de lectura.
-- Necesario para resolver la sesión con el JWT del usuario desde PostgREST.
-- Las políticas existentes siguen limitando perfil, pertenencia y organización.
begin;

grant select on table
    public.profiles,
    public.organization_memberships,
    public.organizations
to authenticated;

-- No se conceden escrituras, acceso a anon ni privilegios sobre otras tablas.
commit;
