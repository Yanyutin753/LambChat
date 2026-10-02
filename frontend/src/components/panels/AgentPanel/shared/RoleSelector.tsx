import React from "react";
import { useTranslation } from "react-i18next";
import { Select } from "../../../common";

interface Role {
  id: string;
  name: string;
}
interface RoleSelectorProps {
  roles: Role[];
  selectedRoleId: string | null;
  onSelectRole: (roleId: string) => void;
  disabled?: boolean;
}

export const RoleSelector = React.memo(function RoleSelector({
  roles,
  selectedRoleId,
  onSelectRole,
  disabled,
}: RoleSelectorProps) {
  const { t } = useTranslation();
  return (
    <Select
      ariaLabel={t("agentConfig.selectRole")}
      value={selectedRoleId ?? ""}
      onChange={onSelectRole}
      disabled={disabled}
      placeholder={t("agentConfig.selectRole")}
      triggerClassName="min-h-11 font-serif"
      options={roles.map((role) => ({
        value: role.id,
        label: <span className="font-serif">{role.name}</span>,
      }))}
    />
  );
});
