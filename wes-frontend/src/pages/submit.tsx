import { useState } from 'react';
import { useRouter } from 'next/router';
import {
  Box,
  Typography,
  Paper,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Grid,
  CircularProgress,
  Alert,
} from '@mui/material';
import Layout from '../components/common/Layout';
import { useSubmitRun, useServiceInfo } from '../hooks/useWesApi';
import { WorkflowSubmission } from '../types/wes';

export default function SubmitPage() {
  const router = useRouter();
  const { data: serviceInfo } = useServiceInfo();
  
  const [formData, setFormData] = useState<WorkflowSubmission>({
    workflow_url: '',
    workflow_type: 'CWL',
    workflow_type_version: '1.0',
    workflow_params: {},
    workflow_engine_parameters: {},
    tags: {},
  });
  
  const [paramsString, setParamsString] = useState('{}');
  const [engineParamsString, setEngineParamsString] = useState('{}');
  const [tagsString, setTagsString] = useState('{}');
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  
  const { mutate: submitRun, isLoading, error } = useSubmitRun({
    onSuccess: (data) => {
      router.push(`/runs/${data.run_id}`);
    },
  });
  
  const handleChange = (field: keyof WorkflowSubmission, value: any) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
    
    // Clear error for this field
    if (formErrors[field]) {
      setFormErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };
  
  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    
    if (!formData.workflow_url) {
      errors.workflow_url = 'Workflow URL is required';
    }
    
    if (!formData.workflow_type) {
      errors.workflow_type = 'Workflow type is required';
    }
    
    if (!formData.workflow_type_version) {
      errors.workflow_type_version = 'Workflow type version is required';
    }
    
    try {
      JSON.parse(paramsString);
    } catch (e) {
      errors.workflow_params = 'Invalid JSON format';
    }
    
    try {
      JSON.parse(engineParamsString);
    } catch (e) {
      errors.workflow_engine_parameters = 'Invalid JSON format';
    }
    
    try {
      JSON.parse(tagsString);
    } catch (e) {
      errors.tags = 'Invalid JSON format';
    }
    
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    const submission: WorkflowSubmission = {
      ...formData,
      workflow_params: JSON.parse(paramsString),
      workflow_engine_parameters: JSON.parse(engineParamsString),
      tags: JSON.parse(tagsString),
    };
    
    submitRun(submission);
  };
  
  return (
    <Layout title="Submit Workflow">
      <Box mb={3}>
        <Typography variant="h4" gutterBottom>
          Submit New Workflow
        </Typography>
        
        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {(error as Error).message}
          </Alert>
        )}
        
        <Paper sx={{ p: 3 }}>
          <form onSubmit={handleSubmit}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Workflow URL"
                  value={formData.workflow_url}
                  onChange={(e) => handleChange('workflow_url', e.target.value)}
                  error={!!formErrors.workflow_url}
                  helperText={formErrors.workflow_url}
                  required
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControl fullWidth error={!!formErrors.workflow_type}>
                  <InputLabel>Workflow Type</InputLabel>
                  <Select
                    value={formData.workflow_type}
                    onChange={(e) => handleChange('workflow_type', e.target.value)}
                    label="Workflow Type"
                    required
                  >
                    {serviceInfo?.workflow_type_versions ? (
                      Object.keys(serviceInfo.workflow_type_versions).map((type) => (
                        <MenuItem key={type} value={type}>
                          {type}
                        </MenuItem>
                      ))
                    ) : (
                      <>
                        <MenuItem value="CWL">CWL</MenuItem>
                        <MenuItem value="WDL">WDL</MenuItem>
                        <MenuItem value="NFL">Nextflow</MenuItem>
                      </>
                    )}
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Workflow Type Version"
                  value={formData.workflow_type_version}
                  onChange={(e) => handleChange('workflow_type_version', e.target.value)}
                  error={!!formErrors.workflow_type_version}
                  helperText={formErrors.workflow_type_version}
                  required
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Workflow Parameters (JSON)"
                  value={paramsString}
                  onChange={(e) => setParamsString(e.target.value)}
                  error={!!formErrors.workflow_params}
                  helperText={formErrors.workflow_params}
                  multiline
                  rows={5}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Workflow Engine Parameters (JSON)"
                  value={engineParamsString}
                  onChange={(e) => setEngineParamsString(e.target.value)}
                  error={!!formErrors.workflow_engine_parameters}
                  helperText={formErrors.workflow_engine_parameters}
                  multiline
                  rows={3}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Tags (JSON)"
                  value={tagsString}
                  onChange={(e) => setTagsString(e.target.value)}
                  error={!!formErrors.tags}
                  helperText={formErrors.tags}
                  multiline
                  rows={3}
                />
              </Grid>
              
              <Grid item xs={12}>
                <Button
                  type="submit"
                  variant="contained"
                  color="primary"
                  size="large"
                  disabled={isLoading}
                  startIcon={isLoading ? <CircularProgress size={24} /> : null}
                >
                  {isLoading ? 'Submitting...' : 'Submit Workflow'}
                </Button>
              </Grid>
            </Grid>
          </form>
        </Paper>
      </Box>
    </Layout>
  );
}
