import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ReviewDecision from '../../../components/humanReview/ReviewDecision/ReviewDecision';

// docs/TEAMMATE_BUG_TRIAGE.md's corrected Low #20: `checklist.every(...)` is
// vacuously true on an empty array, so an application with no checklist
// items at all could be approved without the "every item checked" gate ever
// firing.
function renderDecision(overrides = {}) {
  const onSubmit = vi.fn();
  render(
    <ReviewDecision
      reviewerName="Jane Reviewer"
      decision="APPROVE"
      onDecisionChange={() => {}}
      comments=""
      onCommentsChange={() => {}}
      rejectionReason=""
      onRejectionReasonChange={() => {}}
      checklist={[]}
      corrections={[]}
      submitting={false}
      readOnly={false}
      submitError={null}
      onSubmit={onSubmit}
      {...overrides}
    />
  );
  return { onSubmit };
}

describe('ReviewDecision — empty checklist', () => {
  it('shows the validation error and disables submit for APPROVE with an empty checklist', () => {
    const { onSubmit } = renderDecision();

    expect(
      screen.getByText('Every checklist item must be checked to approve.')
    ).toBeInTheDocument();

    const submitButton = screen.getByRole('button', { name: /submit decision/i });
    expect(submitButton).toBeDisabled();

    fireEvent.click(submitButton);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('allows APPROVE once a non-empty checklist is fully checked', () => {
    const { onSubmit } = renderDecision({
      checklist: [{ item_name: 'Signature present', is_checked: true }],
    });

    expect(
      screen.queryByText('Every checklist item must be checked to approve.')
    ).not.toBeInTheDocument();

    const submitButton = screen.getByRole('button', { name: /submit decision/i });
    expect(submitButton).not.toBeDisabled();

    fireEvent.click(submitButton);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('still blocks APPROVE when a non-empty checklist has an unchecked item', () => {
    renderDecision({
      checklist: [{ item_name: 'Signature present', is_checked: false }],
    });

    expect(
      screen.getByText('Every checklist item must be checked to approve.')
    ).toBeInTheDocument();
  });
});
