import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { IconDocument, IconPlus, IconUpload } from '@/components/icons'
import { LoadingSpinner, PageHeader, EmptyState, Pagination } from '@/components/ui'
import { documentsApi } from '@/services/api'

export default function Documents() {
  const [page, setPage] = useState(1)
  const [showUploadModal, setShowUploadModal] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['documents', page],
    queryFn: () =>
      documentsApi
        .list({ page, limit: 20 })
        .then((r) => r.data),
  })

  return (
    <div>
      <PageHeader
        title="Documents"
        actions={
          <button
            onClick={() => setShowUploadModal(true)}
            className="btn btn-primary"
          >
            <IconPlus className="h-4 w-4 mr-2" />
            Upload Document
          </button>
        }
      />

      <div className="card overflow-hidden">
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-4 text-left">Document</th>
                  <th className="px-6 py-4 text-left">Type</th>
                  <th className="px-6 py-4 text-left">Size</th>
                  <th className="px-6 py-4 text-left">Uploaded</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.map((doc: any) => (
                  <tr key={doc.id} className="table-row">
                    <td className="table-cell">
                      <div className="flex items-center gap-3">
                        <IconDocument className="h-5 w-5 text-archeron-500" />
                        <div>
                          <div className="text-sm font-medium text-archeron-100">
                            {doc.title || doc.filename}
                          </div>
                          <div className="text-xs text-archeron-500">
                            {doc.filename}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="table-cell">
                      <span className="badge badge-neutral">
                        {doc.document_type || doc.mime_type}
                      </span>
                    </td>
                    <td className="table-cell text-archeron-400">
                      {formatFileSize(doc.file_size)}
                    </td>
                    <td className="table-cell text-archeron-400 text-sm">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="table-cell text-right">
                      <button className="btn btn-ghost text-xs py-1.5 px-3">
                        View
                      </button>
                    </td>
                  </tr>
                ))}
                {data?.items?.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <EmptyState message="No documents found" />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={page}
          totalItems={data?.total ?? 0}
          onPageChange={setPage}
          itemLabel="documents"
        />
      </div>

      {showUploadModal && (
        <UploadDocumentModal onClose={() => setShowUploadModal(false)} />
      )}
    </div>
  )
}

function UploadDocumentModal({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [caseId, setCaseId] = useState('')
  const [entityId, setEntityId] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const uploadMutation = useMutation({
    mutationFn: (formData: FormData) => documentsApi.upload(formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      onClose()
    },
  })

  const handleFileSelect = (selectedFile: File) => {
    setFile(selectedFile)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0])
    }
  }

  const handleSubmit = () => {
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)
    if (caseId) formData.append('case_id', caseId)
    if (entityId) formData.append('entity_id', entityId)

    uploadMutation.mutate(formData)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-archeron-900 border border-archeron-700 rounded-lg p-6 max-w-lg w-full">
        <h2 className="text-lg font-semibold text-archeron-100 mb-4">
          Upload Document
        </h2>

        <div className="space-y-4">
          {/* File Drop Zone */}
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              dragOver
                ? 'border-accent-500 bg-accent-500/10'
                : 'border-archeron-700 hover:border-archeron-600'
            }`}
          >
            <IconUpload className="h-12 w-12 text-archeron-500 mx-auto mb-3" />
            {file ? (
              <div>
                <p className="text-sm text-archeron-200 font-medium">
                  {file.name}
                </p>
                <p className="text-xs text-archeron-500 mt-1">
                  {formatFileSize(file.size)}
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm text-archeron-300 mb-1">
                  Drag and drop a file here, or click to browse
                </p>
                <p className="text-xs text-archeron-500">
                  PDF, Word, HTML, text, or email files
                </p>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileSelect(e.target.files[0])
                }
              }}
              accept=".pdf,.doc,.docx,.html,.htm,.txt,.eml,.msg"
            />
          </div>

          {/* Optional Associations */}
          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Case ID (optional)
            </label>
            <input
              type="text"
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="input w-full"
              placeholder="Associate with case..."
            />
          </div>

          <div>
            <label className="block text-sm text-archeron-300 mb-1">
              Entity ID (optional)
            </label>
            <input
              type="text"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              className="input w-full"
              placeholder="Associate with entity..."
            />
          </div>
        </div>

        {uploadMutation.isError && (
          <div className="mt-4 p-3 bg-red-500/10 border border-red-500 rounded text-sm text-red-400">
            {uploadMutation.error instanceof Error
              ? uploadMutation.error.message
              : 'Upload failed'}
          </div>
        )}

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="btn btn-secondary flex-1"
            disabled={uploadMutation.isPending}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="btn btn-primary flex-1"
            disabled={uploadMutation.isPending || !file}
          >
            {uploadMutation.isPending ? 'Uploading...' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  )
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${Math.round(bytes / Math.pow(k, i) * 10) / 10} ${sizes[i]}`
}
