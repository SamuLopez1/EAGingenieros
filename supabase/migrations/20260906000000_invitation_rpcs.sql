-- MVP-04: mutaciones administrativas atómicas para invitaciones de analistas.
-- Solo service_role puede ejecutar estas RPCs; el navegador no recibe esa clave.
begin;

create function public.record_eag_invitation(
    p_invitation_id uuid,
    p_provider_user_id uuid,
    p_organization_id uuid,
    p_email text,
    p_actor_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_organization_id <> '00000000-0000-0000-0000-000000000001'::uuid then
        raise exception 'organization not allowed';
    end if;

    if not exists (
        select 1 from public.organization_memberships
        where user_id = p_actor_id
          and organization_id = p_organization_id
          and role = 'administrador'
    ) then
        raise exception 'administrator membership required';
    end if;

    insert into public.profiles (id) values (p_provider_user_id)
    on conflict (id) do nothing;

    insert into public.organization_memberships (
        user_id, organization_id, role, created_by
    ) values (
        p_provider_user_id, p_organization_id, 'analista', p_actor_id
    );

    insert into public.invitations (
        id, organization_id, email, provider_user_id, status, created_by
    ) values (
        p_invitation_id, p_organization_id, p_email, p_provider_user_id, 'sent', p_actor_id
    );

    insert into public.audit_events (
        organization_id, actor_id, action, target_user_id, invitation_id
    ) values (
        p_organization_id, p_actor_id, 'invitation_created', p_provider_user_id, p_invitation_id
    );
end;
$$;

create function public.revoke_eag_invitation(
    p_invitation_id uuid,
    p_organization_id uuid,
    p_actor_id uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    invited_user_id uuid;
begin
    if not exists (
        select 1 from public.organization_memberships
        where user_id = p_actor_id
          and organization_id = p_organization_id
          and role = 'administrador'
    ) then
        raise exception 'administrator membership required';
    end if;

    select provider_user_id into invited_user_id
    from public.invitations
    where id = p_invitation_id
      and organization_id = p_organization_id
      and status in ('sent', 'resent');

    if invited_user_id is null then
        raise exception 'active invitation not found';
    end if;

    delete from public.organization_memberships
    where user_id = invited_user_id
      and organization_id = p_organization_id;

    update public.invitations
    set status = 'revoked', updated_at = now(), revoked_at = now(), revoked_by = p_actor_id
    where id = p_invitation_id;

    insert into public.audit_events (
        organization_id, actor_id, action, target_user_id, invitation_id
    ) values (
        p_organization_id, p_actor_id, 'invitation_revoked', invited_user_id, p_invitation_id
    );
end;
$$;

revoke all on function public.record_eag_invitation(uuid, uuid, uuid, text, uuid) from public;
revoke all on function public.revoke_eag_invitation(uuid, uuid, uuid) from public;
grant execute on function public.record_eag_invitation(uuid, uuid, uuid, text, uuid) to service_role;
grant execute on function public.revoke_eag_invitation(uuid, uuid, uuid) to service_role;

commit;
