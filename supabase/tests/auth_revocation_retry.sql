-- Offline: aplicar las migraciones antes de ejecutar en una base desechable.
-- PostgreSQL ejecuta la RPC real; la fase de Auth se representa con auth.users.
begin;

insert into auth.users (id, email) values
    ('00000000-0000-0000-0000-000000000010', 'admin@example.test'),
    ('00000000-0000-0000-0000-000000000020', 'invitee@example.test'),
    ('00000000-0000-0000-0000-000000000021', 'analyst@example.test');

insert into public.organization_memberships (user_id, organization_id, role) values
    ('00000000-0000-0000-0000-000000000010',
     '00000000-0000-0000-0000-000000000001', 'administrador'),
    ('00000000-0000-0000-0000-000000000021',
     '00000000-0000-0000-0000-000000000001', 'analista');

do $$
begin
    if not has_function_privilege(
        'service_role', 'public.revoke_eag_invitation(uuid,uuid,uuid)', 'EXECUTE'
    ) or has_function_privilege(
        'authenticated', 'public.revoke_eag_invitation(uuid,uuid,uuid)', 'EXECUTE'
    ) or has_function_privilege(
        'anon', 'public.revoke_eag_invitation(uuid,uuid,uuid)', 'EXECUTE'
    ) then
        raise exception 'unexpected RPC privileges';
    end if;
end;
$$;

set local role service_role;

select public.record_eag_invitation(
    '00000000-0000-0000-0000-000000000030',
    '00000000-0000-0000-0000-000000000020',
    '00000000-0000-0000-0000-000000000001',
    'invitee@example.test',
    '00000000-0000-0000-0000-000000000010'
);

select public.revoke_eag_invitation(
    '00000000-0000-0000-0000-000000000030',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000010'
);

reset role;

do $$
begin
    if exists (
        select 1 from public.organization_memberships
        where user_id = '00000000-0000-0000-0000-000000000020'
    ) or not exists (
        select 1 from auth.users where id = '00000000-0000-0000-0000-000000000020'
    ) then
        raise exception 'expected a removed membership and a remaining Auth user';
    end if;
end;
$$;

-- Simula el fallo externo conservando la fila de Auth entre ambos intentos.
set local role service_role;

do $$
declare
    invitation_id constant uuid := '00000000-0000-0000-0000-000000000030';
    organization_id constant uuid := '00000000-0000-0000-0000-000000000001';
    other_organization_id constant uuid := '00000000-0000-0000-0000-000000000002';
    administrator_id constant uuid := '00000000-0000-0000-0000-000000000010';
    analyst_id constant uuid := '00000000-0000-0000-0000-000000000021';
begin
    begin
        perform public.revoke_eag_invitation(invitation_id, organization_id, analyst_id);
        raise exception 'non-administrator retry was accepted';
    exception when raise_exception then
        if sqlerrm <> 'administrator membership required' then raise; end if;
    end;
    begin
        perform public.revoke_eag_invitation(invitation_id, other_organization_id, administrator_id);
        raise exception 'other organization retry was accepted';
    exception when raise_exception then
        if sqlerrm <> 'administrator membership required' then raise; end if;
    end;
    perform public.revoke_eag_invitation(invitation_id, organization_id, administrator_id);
end;
$$;

reset role;

delete from auth.users where id = '00000000-0000-0000-0000-000000000020';

set local role service_role;

select public.revoke_eag_invitation(
    '00000000-0000-0000-0000-000000000030',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000010'
);

reset role;

do $$
declare
    target_id constant uuid := '00000000-0000-0000-0000-000000000020';
    invitation constant uuid := '00000000-0000-0000-0000-000000000030';
begin
    if exists (select 1 from public.organization_memberships where user_id = target_id)
        or exists (select 1 from auth.users where id = target_id) then
        raise exception 'revoked membership or Auth user remains';
    end if;
    if not exists (
        select 1 from public.invitations where id = invitation and status = 'revoked'
            and provider_user_id = target_id and revoked_at is not null
            and revoked_by = '00000000-0000-0000-0000-000000000010'
    ) or (
        select count(*) from public.audit_events
        where invitation_id = invitation and action = 'invitation_revoked'
    ) <> 1 then
        raise exception 'revocation state or audit count is incorrect';
    end if;
end;
$$;

rollback;
