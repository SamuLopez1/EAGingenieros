-- Prueba de integración PostgreSQL/RLS para el analista sintético del dummy.
-- Ejecutar como postgres, después de las migraciones. No imprime identidades.
-- No modifica filas y todos los cambios de rol/claims son transaccionales.
begin;

do $$
begin
    if not has_table_privilege('service_role', 'public.invitations', 'SELECT') then
        raise exception 'Backend cannot read invitations before revocation';
    end if;
    if not has_table_privilege('authenticated', 'public.invitations', 'SELECT')
        or not has_table_privilege('authenticated', 'public.audit_events', 'SELECT') then
        raise exception 'RLS-protected administrator reads lack SQL privileges';
    end if;
    if has_table_privilege('anon', 'public.invitations', 'SELECT') then
        raise exception 'Anonymous role can read invitations';
    end if;
    if has_table_privilege('authenticated', 'public.invitations', 'UPDATE')
        or has_table_privilege('authenticated', 'public.audit_events', 'INSERT') then
        raise exception 'Authenticated role has administrative write privileges';
    end if;
end;
$$;

do $$
declare
    dummy_user_id uuid;
begin
    select id into dummy_user_id
    from auth.users
    where email = 'eag.analista.dummy@example.com';
    if dummy_user_id is null then
        raise exception 'This check requires the synthetic analyst user';
    end if;
    perform set_config(
        'request.jwt.claim.sub', dummy_user_id::text, true
    );
end;
$$;

set local role authenticated;
do $$
begin
    if not exists (select 1 from public.profiles where id = auth.uid()) then
        raise exception 'Own profile is not readable';
    end if;
    if not exists (
        select 1 from public.organization_memberships
        where user_id = auth.uid() and role in ('administrador', 'analista')
    ) then
        raise exception 'Own membership is not readable';
    end if;
    if not exists (select 1 from public.organizations where slug = 'eag') then
        raise exception 'Member organization is not readable';
    end if;
    if exists (select 1 from public.profiles where id <> auth.uid()) then
        raise exception 'Another user profile is visible';
    end if;
end;
$$;

reset role;
do $$
begin
    -- Identidad sintética sin pertenencia; ningún identificador real se exporta.
    perform set_config('request.jwt.claim.sub',
        '00000000-0000-0000-0000-000000000099', true);
end;
$$;
set local role authenticated;
do $$
begin
    if exists (select 1 from public.organization_memberships)
        or exists (select 1 from public.profiles)
        or exists (select 1 from public.organizations) then
        raise exception 'An unrelated subject can see protected rows';
    end if;
    begin
        update public.organization_memberships set role = 'administrador';
        -- Cero filas visibles/modificadas por RLS también es una denegación.
        if found then
            raise exception 'Unrelated subject changed memberships';
        end if;
    exception when insufficient_privilege then
        null;
    end;
end;
$$;

reset role;
set local role anon;
do $$
begin
    begin
        if exists (select 1 from public.organization_memberships) then
            raise exception 'Anonymous access exposed memberships';
        end if;
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
rollback;
