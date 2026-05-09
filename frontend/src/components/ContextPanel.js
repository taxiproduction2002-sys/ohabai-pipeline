export default function ContextPanel({ conversation }) {
  if (!conversation) {
    return (
      <aside className="context">
        <div className="empty-state-small">No conversation selected</div>
      </aside>
    );
  }

  return (
    <aside className="context">
      <section className="context-section">
        <h3>Contact</h3>
        <div className="context-name">
          {conversation.contact_name || 'Unknown'}
        </div>
        <div className="context-detail">
          {conversation.external_thread_id}
        </div>
      </section>

      <section className="context-section">
        <h3>Notes</h3>
        <div className="placeholder">
          Contact notes will live here.
        </div>
      </section>

      <section className="context-section">
        <h3>AI suggestion</h3>
        <div className="placeholder">
          A suggested reply will appear here.
        </div>
      </section>

      <section className="context-section">
        <h3>Company brain</h3>
        <div className="placeholder">
          Memory blocks relevant to this contact will appear here.
        </div>
      </section>
    </aside>
  );
}
