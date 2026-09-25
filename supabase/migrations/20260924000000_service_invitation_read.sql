-- MVP-04: RLS requiere además privilegio SQL para la lectura autorizada.
-- El backend consulta invitaciones antes de revocarlas o reenviarlas.
-- Solo administradores pueden leer invitaciones y auditoría con su JWT,
-- conforme a las políticas RLS de la migración inicial.
begin;

grant select on table public.invitations to service_role;
grant select on table public.invitations, public.audit_events to authenticated;

commit;
