interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  meta?: string;
}

export function PageHeader({ title, description, actions, meta }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">{title}</h2>
          {meta && (
            <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{meta}</span>
          )}
        </div>
        {description && <p className="text-sm text-muted-foreground mt-0.5">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
