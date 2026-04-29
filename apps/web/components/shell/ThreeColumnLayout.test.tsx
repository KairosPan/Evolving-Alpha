import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ThreeColumnLayout } from './ThreeColumnLayout';

describe('ThreeColumnLayout', () => {
  it('renders all three slots', () => {
    render(
      <ThreeColumnLayout
        left={<div>L</div>} center={<div>C</div>} right={<div>R</div>}
      />
    );
    expect(screen.getByText('L')).toBeInTheDocument();
    expect(screen.getByText('C')).toBeInTheDocument();
    expect(screen.getByText('R')).toBeInTheDocument();
  });
});
