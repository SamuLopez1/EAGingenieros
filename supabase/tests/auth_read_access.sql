-- Prueba de integración PostgreSQL/RLS para el dummy con un único usuario.
-- Ejecutar como postgres, después de las migraciones. No imprime identidades.
-- No modifica filas y todos los cambios de rol/claims son transaccionales.
begin;

do $$
begin
    if (select count(*) from auth.users) <> 1 then
        raise exception 'This check requires exactly one dummy Auth user';
    end if;
    perform set_config(
        'request.jwt.claim.sub', (select id::text from auth.users limit 1), true
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
