-- Fixture manual para el proyecto dummy de MVP-04.
-- Ejecutar solo después de crear ambas cuentas con contraseña y confirmación
-- automática desde Authentication > Users. No contiene ni acepta contraseñas.
-- No es una migración de producción ni se debe aplicar en un proyecto de EAG.
begin;

do $$
declare
    administrator_id uuid;
    analyst_id uuid;
    eag_organization_id constant uuid := '00000000-0000-0000-0000-000000000001';
begin
    select id into administrator_id
    from auth.users
    where email = 'eag.admin.dummy@example.com';

    select id into analyst_id
    from auth.users
    where email = 'eag.analista.dummy@example.com';

    if administrator_id is null or analyst_id is null then
        raise exception 'Create the two synthetic password users before running this fixture';
    end if;

    if exists (
        select 1 from public.organization_memberships
        where user_id = administrator_id
          and (organization_id <> eag_organization_id or role <> 'administrador')
    ) or exists (
        select 1 from public.organization_memberships
        where user_id = analyst_id
          and (organization_id <> eag_organization_id or role <> 'analista')
    ) then
        raise exception 'A synthetic user already has an unexpected membership';
    end if;

    insert into public.profiles (id)
    values (administrator_id), (analyst_id)
    on conflict (id) do nothing;

    insert into public.organization_memberships (user_id, organization_id, role)
    values
        (administrator_id, eag_organization_id, 'administrador'),
        (analyst_id, eag_organization_id, 'analista')
    on conflict (user_id) do nothing;

    insert into public.audit_events (organization_id, action, target_user_id, metadata)
    select eag_organization_id, 'membership_assigned', candidate.user_id,
           '{"fixture":"dummy_password_users"}'::jsonb
    from (values (administrator_id), (analyst_id)) as candidate(user_id)
    where not exists (
        select 1
        from public.audit_events event
        where event.action = 'membership_assigned'
          and event.target_user_id = candidate.user_id
          and event.metadata = '{"fixture":"dummy_password_users"}'::jsonb
    );
end;
$$;

commit;
