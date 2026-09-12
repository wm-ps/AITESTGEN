import { useState, type InputHTMLAttributes } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEye, faEyeSlash } from '@fortawesome/free-solid-svg-icons'

export function PasswordInput({ style, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  const [visible, setVisible] = useState(false)

  return (
    <div style={{ position: 'relative' }}>
      <input {...props} type={visible ? 'text' : 'password'} style={{ ...style, width: '100%', paddingRight: 40 }} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        style={{
          position: 'absolute',
          right: 8,
          top: '50%',
          transform: 'translateY(-50%)',
          background: 'none',
          border: 'none',
          padding: 4,
          display: 'flex',
          color: 'var(--fg-4)',
          cursor: 'pointer',
        }}
      >
        <FontAwesomeIcon icon={visible ? faEyeSlash : faEye} style={{ fontSize: 15 }} />
      </button>
    </div>
  )
}
